import atexit
import os
import platform
import re
import shutil
import signal
import subprocess
import threading
import time
import traceback
import uuid
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import yt_dlp

from stahovac.config.constants import FORMAT_MP4, QUALITY_BEST, MediaFormat
from stahovac.core.ffmpeg import find_ffmpeg
from stahovac.core.metadata import MetadataService, YtdlLogger
from stahovac.core.validator import pad_time, time_to_seconds
from stahovac.models import DownloadParams, DownloadState
from stahovac.platforms import _platform_for, platform_opts
from stahovac.storage.history import HistoryManager
from stahovac.utils.cookies import resolve_cookies_opts
from stahovac.utils.format import format_eta as _format_eta
from stahovac.utils.format import format_speed as _format_speed

_CHILD_PROCESSES: set[subprocess.Popen] = set()
_CHILD_PROCESSES_LOCK = threading.Lock()

JOBS_DIR_NAME = ".jobs"
AETHER_KEEP_FAILED_JOBS = "AETHER_KEEP_FAILED_JOBS"

_RE_FFMPEG_TIME = re.compile(r"time=(\d+):(\d+):(\d+)")


def _kill_process(proc: subprocess.Popen) -> None:
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=3)
            except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    except (OSError, subprocess.SubprocessError):
        pass


def _cleanup_child_processes():
    with _CHILD_PROCESSES_LOCK:
        procs = list(_CHILD_PROCESSES)
        _CHILD_PROCESSES.clear()
    for proc in procs:
        _kill_process(proc)


def _track_process(proc: subprocess.Popen) -> None:
    with _CHILD_PROCESSES_LOCK:
        _CHILD_PROCESSES.add(proc)


def _untrack_process(proc: subprocess.Popen) -> None:
    with _CHILD_PROCESSES_LOCK:
        _CHILD_PROCESSES.discard(proc)


atexit.register(_cleanup_child_processes)


def _find_job_file(directory: Path) -> Path | None:
    for f in directory.iterdir():
        if f.is_file():
            return f
    return None


def _unique_dest(dest_dir: Path, name: str) -> Path:
    """Cílová cesta, která nikdy nepřepíše existující soubor.

    Pokud soubor ``name`` už v cílové složce existuje, přidá se číselná
    přípona (``Soubor (1).mp4``, ``Soubor (2).mp4``, ...).
    """
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for i in range(1, 1000):
        candidate = dest_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return dest


def _build_ydl_opts(
    params: DownloadParams,
    config: dict[str, Any],
    progress_hook,
) -> dict:
    url = params.url
    quality = params.quality
    format_choice = params.format_choice
    output_folder = params.output_folder

    is_audio = MediaFormat.MP3.value in format_choice
    is_subs = MediaFormat.SUBS.value in format_choice

    opts: dict = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "logger": YtdlLogger(),
        "concurrent_fragments": 5,
        "fragment_retries": 10,
        "progress_hooks": [progress_hook],
        "socket_timeout": 15,
        "retries": 5,
        "extractor_retries": 3,
        "file_access_retries": 3,
        "js_runtimes": {"node": {}},
    }

    cookies_opts = resolve_cookies_opts(config, url)
    opts.update(cookies_opts)
    opts.update(Downloader._platform_opts(url))

    if is_subs:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitlesformat"] = "srt/best"
        opts["skip_download"] = True
        opts["postprocessors"] = [
            {
                "key": "FFmpegSubtitlesConvertor",
                "format": "srt",
            }
        ]
    elif is_audio:
        opts["format"] = "bestaudio/best"
        opts["format_sort"] = ["res:0", "vcodec", "br"]
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ]
    else:
        opts["format"] = "bestvideo+bestaudio/best"
        opts["merge_output_format"] = "mp4"

    if quality != QUALITY_BEST and not is_audio and not is_subs:
        height = quality.replace("p", "")
        opts["format_sort"] = [f"res:{height}", "codec:av1:mpeg4"]

    name = "%(title)s"
    if is_subs:
        name += " [SUBS]"
    elif quality != QUALITY_BEST and not is_audio:
        name += f" [{quality}]"
    elif is_audio:
        name += " [MP3]"
    opts["outtmpl"] = str(Path(output_folder) / f"{name}.%(ext)s")
    opts["overwrites"] = False

    ffmpeg_bin = find_ffmpeg()
    if ffmpeg_bin is not None:
        opts["ffmpeg_location"] = str(ffmpeg_bin.parent)

    return opts


def _estimate_cut_duration(start_time: str, end_time: str, end_option: str | None) -> int | None:
    if not end_option or end_option == "Do konce videa":
        return None
    from stahovac.core.validator import time_to_seconds

    return max(0, time_to_seconds(end_time) - time_to_seconds(start_time))


def _ffmpeg_timeout(estimated_secs: int | None, re_encode: bool) -> float:
    if estimated_secs and estimated_secs > 0:
        factor = 5 if re_encode else 2
        return max(60.0, estimated_secs * factor + 60.0)
    return 7200.0


def _fmt_timestamp(value: str) -> str:
    parts = value.split(":")
    if len(parts) == 3:
        return f"{parts[0]}h{parts[1]}m{parts[2]}s"
    if len(parts) == 2:
        return f"{parts[0]}m{parts[1]}s"
    return f"{parts[0]}s"


def _build_ffmpeg_cmd(
    input_path: Path,
    start_time: str,
    end_time: str,
    end_option: str,
    re_encode: bool = False,
    crf: int = 23,
    preset: str = "fast",
    ffmpeg_bin: str = "ffmpeg",
) -> tuple[list[str], Path]:
    from stahovac.core.validator import pad_time

    start_padded = pad_time(start_time)
    start_safe = _fmt_timestamp(start_padded)

    if end_option == "Do konce videa":
        to_arg: str | None = None
        section_part = f" [{start_safe}-inf]"
    else:
        to_arg = pad_time(end_time)
        end_safe = _fmt_timestamp(to_arg)
        section_part = f" [{start_safe} - {end_safe}]"

    output_path = input_path.with_name(f"{input_path.stem}{section_part}{input_path.suffix}")

    if re_encode:
        cmd = [ffmpeg_bin, "-y", "-i", str(input_path), "-ss", start_padded]
        if to_arg:
            cmd.extend(["-to", to_arg])
        cmd.extend(["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-c:a", "aac"])
    else:
        cmd = [ffmpeg_bin, "-y", "-ss", start_padded, "-i", str(input_path)]
        if to_arg:
            cmd.extend(["-to", to_arg])
        cmd.extend(["-c", "copy", "-avoid_negative_ts", "make_zero"])
    cmd.extend(["-movflags", "+faststart", str(output_path)])
    return cmd, output_path


def _can_ranged_hls(url: str) -> bool:
    """Jen platformy s HLS obsahem umí stáhnout úsek přímo ze segmentů."""
    module = _platform_for(url)
    return module is not None and bool(getattr(module, "ranged_hls", False))


def _headers_args(headers: dict) -> list[str]:
    if not headers:
        return []
    value = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    return ["-headers", value]


def _hls_input_args(fmt: dict) -> list[str]:
    args = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    args += _headers_args(fmt.get("http_headers") or {})
    args += ["-i", fmt["url"]]
    return args


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

    stem: str = sanitize_filename(title)
    if quality != QUALITY_BEST:
        stem += f" [{quality}]"
    start_safe = _fmt_timestamp(pad_time(start_time))
    if end_option == "Do konce videa":
        stem += f" [{start_safe}-inf]"
    else:
        end_safe = _fmt_timestamp(pad_time(end_time))
        stem += f" [{start_safe} - {end_safe}]"
    return stem + ".mp4"


def _build_ranged_cmd(
    video_fmt: dict,
    audio_fmt: dict | None,
    start_time: str,
    end_time: str,
    end_option: str,
    re_encode: bool,
    crf: int,
    preset: str,
    output_path: Path,
    ffmpeg_bin: str,
) -> list[str]:
    """FFmpeg příkaz, který z HLS streamu stáhne jen segmenty v časovém rozsahu."""
    cmd = [ffmpeg_bin, "-y", "-ss", pad_time(start_time)]
    cmd += _hls_input_args(video_fmt)
    if audio_fmt is not None:
        cmd += _hls_input_args(audio_fmt)
    if end_option != "Do konce videa":
        duration = max(0, time_to_seconds(end_time) - time_to_seconds(start_time))
        cmd += ["-t", str(duration)]
    if re_encode:
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-c:a", "aac"]
    else:
        cmd += ["-c", "copy", "-bsf:a", "aac_adtstoasc", "-avoid_negative_ts", "make_zero"]
    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


class Downloader:
    def __init__(self, config: dict[str, Any]):
        self._config = config
        self._metadata = MetadataService()
        self.is_cancelled = False
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._finish_fired = False

        self.on_log = lambda text: None
        self.on_progress = lambda job_id, percent, speed, eta: None
        self.on_status = lambda job_id, text, color: None
        self.on_finish = lambda job_id, success, message: None
        self.on_state = lambda state: None

    @property
    def metadata(self) -> MetadataService:
        return self._metadata

    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self.is_cancelled = True
        self._cancel_event.set()

    def force_stop(self) -> None:
        """Nouzové zastavení: zruší úlohu a ukončí známé child procesy (např. FFmpeg).

        Používá se jako poslední záchrana, kdy běžný `cancel()` nestačí.
        Worker po ukončení child procesů skončí a v `finally` uklidí job adresář.
        """
        self.cancel()
        _cleanup_child_processes()

    def start(self, params: DownloadParams, job_id: str | None = None) -> bool:
        job_id = job_id or uuid.uuid4().hex
        with self._lock:
            if self.is_busy():
                return False
            self.is_cancelled = False
            self._cancel_event.clear()
            self._finish_fired = False
            self._thread = threading.Thread(target=self._download_worker, args=(params, job_id), daemon=True)
            self._thread.start()
            return True

    def _finish_once(self, job_id: str, success: bool, message: str) -> None:
        """Zavolá `on_finish` právě jednou (chrání před duplicitami z více větví workeru)."""
        if self._finish_fired:
            return
        self._finish_fired = True
        self.on_finish(job_id, success, message)

    def _set_state(self, state: DownloadState) -> None:
        self.on_state(state)

    def _progress_hook(self, job_id: str, d: dict) -> None:
        if self._cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Stahování zrušeno uživatelem")
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            percent = (downloaded / total * 100) if total > 0 else 0
            speed = _format_speed(d.get("speed"))
            eta = _format_eta(d.get("eta"))
            self.on_progress(job_id, percent, speed, eta)
        elif d["status"] == "finished":
            self.on_status(job_id, "Dokončeno, zpracovávám…", "orange")

    def _finish_cancelled(self, job_id: str) -> None:
        """Zrušení uživatelem: vždy nastaví finální status, aby se UI neviselo."""
        self.on_status(job_id, "Stahování zrušeno.", "orange")
        self._set_state(DownloadState.CANCELLED)
        self._finish_once(job_id, False, "Zrušeno")

    def _download_worker(self, params: DownloadParams, job_id: str) -> None:
        url = params.url
        output_folder = params.output_folder
        job_dir = Path(output_folder) / JOBS_DIR_NAME / job_id
        success = False

        try:
            Path(output_folder).mkdir(parents=True, exist_ok=True)
            job_dir.mkdir(parents=True, exist_ok=True)

            if self.is_cancelled:
                self._finish_cancelled(job_id)
                return

            self._set_state(DownloadState.FETCHING_METADATA)
            self.on_status(job_id, "Načítám info o videu…", "orange")
            video_title = self._get_title(url)
            if self.is_cancelled:
                self._finish_cancelled(job_id)
                return

            opts = _build_ydl_opts(params, self._config, lambda d: self._progress_hook(job_id, d))
            opts["outtmpl"] = str(job_dir / "%(title)s.%(ext)s")
            opts["overwrites"] = False
            opts["paths"] = {"home": str(job_dir)}
            opts["_job_id"] = job_id
            opts["_job_dir"] = str(job_dir)
            opts["_cancel_check"] = self._cancel_event.is_set

            self._set_state(DownloadState.DOWNLOADING)
            ranged_path: Path | None = None
            ok = False
            if not params.whole_video and params.format_choice == FORMAT_MP4 and _can_ranged_hls(url):
                ranged_path = self._ranged_download(params, url, job_id, job_dir)
                if ranged_path is not None:
                    self.on_log("Úsek stažen přímo z HLS segmentů – celé video se nestahovalo.")
                    ok = True
                else:
                    self.on_log("Stažení úseku z HLS segmentů se nepodařilo – stahuji celé video a ořezávám lokálně.")
            if not ok:
                ok = self._download_with_ytdlp(url, opts, job_id)
            if self.is_cancelled:
                self._finish_cancelled(job_id)
                return

            if ok:
                is_subs_dl = params.format_choice == MediaFormat.SUBS.value
                if ranged_path is not None:
                    fpath = self._move_output_files(job_dir, output_folder)
                else:
                    found = _find_job_file(job_dir)
                    if not found:
                        self.on_log("Chyba: yt-dlp skončil, ale nenalezen žádný výstupní soubor.")
                        self.on_status(job_id, "Stahování se nezdařilo – nenalezen výstupní soubor.", "orange")
                        self._finish_fail(job_id)
                        return
                    elif found and not params.whole_video and not is_subs_dl:
                        self._set_state(DownloadState.PROCESSING)
                        self.on_status(job_id, "Ořezávám video…", "orange")
                        trimmed = self._cut_with_ffmpeg(
                            found,
                            params.start_time,
                            params.end_time,
                            params.end_option,
                            re_encode=params.re_encode,
                            crf=self._safe_crf(params.crf),
                            preset=params.preset,
                            job_id=job_id,
                        )
                        if self.is_cancelled:
                            self._finish_cancelled(job_id)
                            return
                        if trimmed:
                            found.unlink(missing_ok=True)
                            fpath = self._move_output_files(job_dir, output_folder)
                        else:
                            self.on_status(job_id, "Ořez se nezdařil. Původní soubor byl zachován.", "orange")
                            fpath = self._move_output_files(job_dir, output_folder)
                    else:
                        fpath = self._move_output_files(job_dir, output_folder)
                self._finish_success(job_id, video_title, url, fpath, params.format_choice)
                success = True
            else:
                self._finish_fail(job_id)

        except yt_dlp.utils.YoutubeDLError as e:
            err = str(e)
            self.on_log(f"Stahování selhalo: {err[:300]}")
            self._report_download_error(err, job_id)
            self._finish_once(job_id, False, "Stahování selhalo")
        except Exception:
            self.on_log(f"Kritická výjimka: {traceback.format_exc()}")
            self.on_status(job_id, "Aplikaci nastala chyba. Podrobnosti v logu.", "orange")
            self._finish_once(job_id, False, "Operace se nezdařila")
        finally:
            keep_failed = os.environ.get(AETHER_KEEP_FAILED_JOBS, "") == "1" and not success
            if keep_failed:
                self.on_log(f"Debug: pracovní adresář zachován ({AETHER_KEEP_FAILED_JOBS}=1): {job_dir}")
            else:
                shutil.rmtree(job_dir, ignore_errors=True)
            if not success:
                if not self._finish_fired:
                    self.on_status(job_id, "Operace se nezdařila.", "orange")
                self._finish_once(job_id, False, "Worker finished")

    def _move_output_files(self, job_dir: Path, output_folder: str) -> str | None:
        dest_dir = Path(output_folder)
        dest_dir.mkdir(parents=True, exist_ok=True)
        moved: list[Path] = []
        for f in sorted(job_dir.iterdir()):
            if f.is_file():
                dest = _unique_dest(dest_dir, f.name)
                os.replace(f, dest)
                moved.append(dest)
        if not moved:
            return None
        largest = max(moved, key=lambda p: p.stat().st_size)
        return str(largest)

    def _cleanup_output(self, opts: dict) -> None:
        job_dir = opts.get("_job_dir")
        if not job_dir:
            return
        d = Path(job_dir)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            self.on_log(f"Smazán neúplný pracovní adresář: {d.name}")

    def _download_with_ytdlp(self, url: str, opts: dict, job_id: str) -> bool:
        max_attempts = 3
        self.on_status(job_id, "Stahuji…", "blue")
        for attempt in range(1, max_attempts + 1):
            try:
                if self._cancel_event.is_set():
                    self._cleanup_output(opts)
                    return False
                ydl = yt_dlp.YoutubeDL(opts)
                ydl.download([url])
                return True
            except yt_dlp.utils.DownloadCancelled:
                self.on_log("Stahování zrušeno uživatelem")
                self._cleanup_output(opts)
                return False
            except yt_dlp.utils.DownloadError as e:
                err = str(e)
                if "zrušeno" in err.lower():
                    self._cleanup_output(opts)
                    return False
                if "Unable to download video subtitles" in err:
                    self.on_log(f"Titulky nebyly zcela staženy: {err[:200]}")
                    self.on_status(job_id, "Titulky staženy (některé jazyky nemusí být k dispozici).", "green")
                    return True
                if attempt < max_attempts and self._is_transient_error(err):
                    if self._cancel_event.wait(timeout=2 * attempt):
                        self._cleanup_output(opts)
                        self.on_log("Stahování zrušeno uživatelem")
                        return False
                    self.on_log(f"Přechodná chyba, zkouším znovu ({attempt}/{max_attempts - 1}): {err[:200]}")
                    continue
                self._report_download_error(err, job_id)
                self._cleanup_output(opts)
                self.on_log(err[:300])
                return False
            except yt_dlp.utils.YoutubeDLError as ex:
                self.on_log(f"Chyba yt-dlp: {ex}")
                self.on_status(job_id, f"Chyba při stahování: {ex}", "orange")
                self._cleanup_output(opts)
                return False
            except Exception as ex:
                self.on_log(f"Neočekávaná chyba: {ex}")
                self.on_status(job_id, "Neočekávaná chyba při stahování.", "orange")
                self._cleanup_output(opts)
                return False
        return False  # pragma: no cover – smyčka retry vždy vrací v některé větvi

    @staticmethod
    def _is_transient_error(err: str) -> bool:
        markers = (
            "http error 403",
            "http error 408",
            "http error 410",
            "http error 429",
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
            "timed out",
            "timeout",
            "connection reset",
            "connection",
            "rate limit",
            "temporary failure in name resolution",
            "unable to download json metadata",
            "unable to download webpage",
            "unable to download video data",
            "forbidden",
        )
        low = err.lower()
        return any(marker in low for marker in markers)

    def _report_download_error(self, err: str, job_id: str) -> None:
        if "403" in err or "Forbidden" in err:
            self.on_status(
                job_id,
                "Přístup zamítnut (403). Soukromý obsah vyžaduje přihlášení/cookies v Nastavení; "
                "jinak může jít o dočasné omezení – zkus to znovu později.",
                "orange",
            )
        elif "429" in err or "rate limit" in err.lower() or "http error 410" in err.lower():
            self.on_status(
                job_id,
                "Dočasné omezení ze strany serveru (příliš mnoho požadavků). Počkej chvíli a zkus to znovu.",
                "orange",
            )
        elif "404" in err or "Video unavailable" in err or "not found (deleted or unavailable)" in err:
            self.on_status(job_id, "Video není dostupné nebo bylo smazáno.", "orange")
        elif "registered users" in err:
            self.on_status(job_id, "Video vyžaduje přihlášení – použij cookies.", "orange")
        else:
            self.on_status(job_id, f"Stahování selhalo: {err[:200]}", "orange")

    def _get_title(self, url: str) -> str:
        extra_opts = self._platform_opts(url)
        meta = self._metadata.get_cached(url) or self._metadata.fetch_sync(
            url,
            self._config,
            cancel_check=lambda: self.is_cancelled,
            extra_opts=extra_opts,
        )
        return meta.title if meta else url

    @staticmethod
    def _safe_crf(value: object) -> int:
        try:
            crf = int(value)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return 23
        return crf if 0 <= crf <= 51 else 23

    @staticmethod
    def _platform_opts(url: str) -> dict:
        return platform_opts(url)

    def _cut_with_ffmpeg(
        self,
        input_path: Path,
        start_time: str,
        end_time: str,
        end_option: str,
        re_encode: bool = False,
        crf: int = 23,
        preset: str = "fast",
        job_id: str = "",
    ) -> Path | None:
        ffmpeg_bin = find_ffmpeg()
        if ffmpeg_bin is None:
            self.on_log("FFmpeg není nainstalován. Ořez není možný.")
            return None

        cmd, output_path = _build_ffmpeg_cmd(
            input_path,
            start_time,
            end_time,
            end_option,
            re_encode=re_encode,
            crf=crf,
            preset=preset,
            ffmpeg_bin=str(ffmpeg_bin),
        )
        self.on_log(f"Ořezávám: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        _track_process(proc)
        try:
            estimated = _estimate_cut_duration(start_time, end_time, end_option)
            ok = self._run_ffmpeg(proc, estimated, re_encode, job_id)
            if ok and output_path.exists():
                return output_path
            return None
        finally:
            _untrack_process(proc)

    def _ranged_download(self, params: DownloadParams, url: str, job_id: str, job_dir: Path) -> Path | None:
        """Stáhne z HLS streamu (Kick/Twitch) pouze segmenty v časovém rozsahu ořezu.

        Celé video se nestahuje – FFmpeg ze serveru vyžádá jen segmenty, které
        pokrývají `[start, end]`. Při neúspěchu vrací `None` a volající se vrátí
        k běžnému stažení celého videa.
        """
        ffmpeg_bin = find_ffmpeg()
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
        except yt_dlp.utils.YoutubeDLError as e:
            self.on_log(f"Ranged stahování úseku přeskočeno: {e}")
            return None
        if self.is_cancelled:
            return None

        video_fmt, audio_fmt = _select_hls_formats(info, params.quality)
        if not video_fmt:
            self.on_log("Pro danou kvalitu není k dispozici HLS formát.")
            return None

        title = self._get_title(url)
        if self.is_cancelled:
            return None
        output_path = job_dir / _ranged_output_name(
            title, params.quality, params.start_time, params.end_time, params.end_option
        )
        temp_path = job_dir / "ranged.tmp.mp4"
        cmd = _build_ranged_cmd(
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
        self.on_log(f"Stahuji jen úsek (HLS): {' '.join(cmd)}")
        self.on_status(job_id, "Stahuji jen vybraný úsek (HLS)…", "blue")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        _track_process(proc)
        try:
            estimated = _estimate_cut_duration(params.start_time, params.end_time, params.end_option)
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
            _untrack_process(proc)

    def _run_ffmpeg(self, proc: subprocess.Popen, estimated_secs: int | None, re_encode: bool, job_id: str) -> bool:
        """Spustí FFmpeg a sleduje průběh.

        Výstup se čte v samostatném vlákně, takže cyklus pravidelně
        kontroluje zrušení a časový limit i v případě, kdy FFmpeg dočasně
        neposílá žádný výstup (na rozdíl od blokujícího ``readline()``).
        """
        started = time.time()
        timeout = _ffmpeg_timeout(estimated_secs, re_encode)
        lines: Queue[str] = Queue()
        stopped = threading.Event()

        def _read_stderr():
            stderr = proc.stderr
            try:
                if stderr is not None:
                    while True:
                        line = stderr.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
                        lines.put(text)
            except (OSError, ValueError):
                pass
            finally:
                stopped.set()

        if self._cancel_event.is_set():
            self.on_log("Ořez zrušen uživatelem")
            _kill_process(proc)
            return False

        reader = threading.Thread(target=_read_stderr, name="ffmpeg-stderr", daemon=True)
        reader.start()

        while True:
            if self._cancel_event.is_set():
                self.on_log("Ořez zrušen uživatelem")
                _kill_process(proc)
                stopped.set()
                reader.join(timeout=1)
                return False
            if time.time() - started > timeout:
                self.on_log("Ořezávání přesáhlo časový limit, ukončuji.")
                _kill_process(proc)
                stopped.set()
                reader.join(timeout=1)
                return False
            try:
                text = lines.get(timeout=0.2)
            except Empty:
                if stopped.is_set() and lines.empty():
                    break
                continue
            m = _RE_FFMPEG_TIME.search(text)
            if m and estimated_secs and estimated_secs > 0:
                hours, minutes, seconds = (int(g) for g in m.groups())
                elapsed = hours * 3600 + minutes * 60 + seconds
                percent = min(100.0, elapsed / estimated_secs * 100)
                self.on_progress(job_id, percent, "–", "–")

        try:
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            _kill_process(proc)
            return False
        return proc.returncode == 0

    def _finish_success(
        self, job_id: str, title: str, url: str, file_path: str | None, format_choice: str = ""
    ) -> None:
        if MediaFormat.SUBS.value in format_choice:
            msg = "Titulky (SRT) úspěšně staženy!"
        elif MediaFormat.MP3.value in format_choice:
            msg = "Zvuk (MP3) úspěšně stažen!"
        else:
            msg = "Video (MP4) úspěšně staženo!"
        self.on_status(job_id, msg, "green")
        self.on_log("Hotovo! Soubor úspěšně uložen.")
        if file_path:
            HistoryManager.append(title, url, file_path)
        self._set_state(DownloadState.FINISHED)
        self._finish_once(job_id, True, "Úspěch")

    def _finish_fail(self, job_id: str) -> None:
        self.on_status(job_id, "Stahování se nezdařilo. Podrobnosti v logu.", "orange")
        self._set_state(DownloadState.FAILED)
        self._finish_once(job_id, False, "Stahování selhalo")
