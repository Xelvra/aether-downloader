"""Ranged stahování úseků přímo z HLS segmentů (Kick/Twitch).

Vyděleno z `core/downloader.py` (audit §6.1). `HlsRangedMixin` se míchá do
`Downloader`; na `stahovac.core.downloader` se odkazujeme přes ``dl_mod``
za běhu kvůli monkeypatchování v testech. ``import dl_mod`` je schválně až
na konci souboru.
"""

import os
import threading
from collections.abc import Callable
from pathlib import Path

from stahovac.config.constants import END_OPTION_FULL, QUALITY_BEST
from stahovac.core._ffmpeg import FfmpegTrimMixin, _fmt_timestamp
from stahovac.core.metadata import MetadataError, MetadataService
from stahovac.core.validator import pad_time
from stahovac.utils.paths import truncate_filename


def _can_ranged_hls(url: str) -> bool:
    """Jen platformy s HLS obsahem umí stáhnout úsek přímo ze segmentů."""
    from stahovac.platforms import _platform_for

    module = _platform_for(url)
    return module is not None and bool(getattr(module, "ranged_hls", False))


def _closest_height_format(videos: list[dict], target: int) -> dict | None:
    if not videos:
        return None
    at_most = [f for f in videos if (f.get("height") or 0) <= target]
    pool = at_most or videos
    return max(pool, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))


def _select_hls_formats(info: dict | None, quality: str) -> tuple[dict | None, dict | None]:
    """Vybere HLS video (a případně samostatné audio) pro požadovanou kvalitu."""
    if not info:
        return None, None
    formats = info.get("formats") or []
    hls = [f for f in formats if f.get("protocol") in ("m3u8_native", "m3u8") and f.get("url")]
    if not hls:
        return None, None

    videos = [f for f in hls if f.get("vcodec") and f.get("vcodec") != "none"]
    audios = [f for f in hls if f.get("acodec") and (not f.get("vcodec") or f.get("vcodec") == "none")]
    if not videos:
        return None, None

    if quality == QUALITY_BEST:
        video_fmt = max(videos, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
    else:
        try:
            target = int(quality.replace("p", ""))
        except ValueError:
            target = 0
        video_fmt = _closest_height_format(videos, target)

    muxed = bool(video_fmt.get("acodec")) and video_fmt.get("acodec") != "none"
    audio_fmt = None
    if not muxed and audios:
        audio_fmt = max(audios, key=lambda f: f.get("tbr") or 0)
    return video_fmt, audio_fmt


def _ranged_output_name(title: str, quality: str, start_time: str, end_time: str, end_option: str) -> str:
    from yt_dlp.utils import sanitize_filename

    stem: str = truncate_filename(sanitize_filename(title))
    if quality != QUALITY_BEST:
        stem += f" [{quality}]"
    start_safe = _fmt_timestamp(pad_time(start_time))
    if end_option == END_OPTION_FULL:
        stem += f" [{start_safe}-inf]"
    else:
        end_safe = _fmt_timestamp(pad_time(end_time))
        stem += f" [{start_safe} - {end_safe}]"
    return stem + ".mp4"


class HlsRangedMixin(FfmpegTrimMixin):
    _cancel_event: threading.Event
    _config: dict
    _metadata: MetadataService
    is_cancelled: bool
    on_log: Callable[[str], None]
    on_status: Callable[[str, str, str], None]
    _platform_opts: Callable[[str], dict]
    _safe_crf: Callable[[object], int]
    _get_title: Callable[[str], str]

    def _ranged_download(self, params, url: str, job_id: str, job_dir: Path) -> Path | None:
        """Stáhne z HLS streamu (Kick/Twitch) pouze segmenty v časovém rozsahu ořezu.

        Celé video se nestahuje – FFmpeg ze serveru vyžádá jen segmenty, které
        pokrývají `[start, end]`. Při neúspěchu vrací `None` a volající se vrátí
        k běžnému stažení celého videa.
        """
        ffmpeg_bin = dl_mod.find_ffmpeg()
        if ffmpeg_bin is None:
            self.on_log("Ranged stahování úseku vyžaduje FFmpeg.")
            return None

        extra_opts = self._platform_opts(url)
        try:
            info = self._metadata.fetch_info(
                url,
                self._config,
                extra_opts=extra_opts,
                cancel_check=self._cancel_event.is_set,
            )
        except MetadataError as e:
            self.on_log(f"Ranged stahování úseku přeskočeno: {e}")
            return None
        if self.is_cancelled:
            return None

        video_fmt, audio_fmt = dl_mod._select_hls_formats(info, params.quality)
        if not video_fmt:
            self.on_log("Pro danou kvalitu není k dispozici HLS formát.")
            return None

        title = self._get_title(url)
        if self.is_cancelled:
            return None
        output_path = job_dir / dl_mod._ranged_output_name(
            title, params.quality, params.start_time, params.end_time, params.end_option
        )
        temp_path = job_dir / "ranged.tmp.mp4"
        cmd = dl_mod._build_ranged_cmd(
            video_fmt,
            audio_fmt,
            params.start_time,
            params.end_time,
            params.end_option,
            params.re_encode,
            self._safe_crf(params.crf),
            params.preset,
            temp_path,
            str(ffmpeg_bin),
        )
        self.on_log(f"Stahuji jen úsek (HLS): {dl_mod._sanitize_cmd(cmd)}")
        self.on_status(job_id, "Stahuji jen vybraný úsek (HLS)…", "blue")
        proc = dl_mod.subprocess.Popen(
            cmd,
            stdout=dl_mod.subprocess.DEVNULL,
            stderr=dl_mod.subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        dl_mod._track_process(proc)
        try:
            estimated = dl_mod._estimate_cut_duration(params.start_time, params.end_time, params.end_option)
            ok = self._run_ffmpeg(proc, estimated, params.re_encode, job_id)
            if self.is_cancelled:
                temp_path.unlink(missing_ok=True)
                return None
            if ok and temp_path.exists() and temp_path.stat().st_size > 0:
                os.replace(temp_path, output_path)
                return output_path
            temp_path.unlink(missing_ok=True)
            return None
        finally:
            dl_mod._untrack_process(proc)


import stahovac.core.downloader as dl_mod  # noqa: E402  (cyklický import – jen runtime přístup)
