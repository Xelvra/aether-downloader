"""yt-dlp stahování: opce, retry s backoffem a klasifikace chyb.

Vyděleno z `core/downloader.py` (audit §6.1). `YtDlpMixin` se míchá do
`Downloader`; na `stahovac.core.downloader` se odkazujeme přes ``dl_mod``
za běhu kvůli monkeypatchování v testech. ``import dl_mod`` je schválně až
na konci souboru.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from stahovac.config.constants import (
    QUALITY_BEST,
    STATUS_BLUE,
    STATUS_DOWNLOADING,
    STATUS_FINISHED_PROCESSING,
    STATUS_GREEN,
    STATUS_ORANGE,
    YTDLP_CONCURRENT_FRAGMENTS,
    YTDLP_EXTRACTOR_RETRIES,
    YTDLP_FILE_ACCESS_RETRIES,
    YTDLP_FRAGMENT_RETRIES,
    YTDLP_MAX_ATTEMPTS,
    YTDLP_RETRIES,
    YTDLP_SOCKET_TIMEOUT,
    MediaFormat,
)
from stahovac.core.metadata import YtdlLogger
from stahovac.models import DownloadParams
from stahovac.platforms import platform_opts
from stahovac.utils.cookies import resolve_cookies_opts
from stahovac.utils.format import format_eta as _format_eta
from stahovac.utils.format import format_speed as _format_speed


def _ensure_ffmpeg_ready() -> None:
    """Počká, až bude FFmpeg k dispozici, když ho úloha vyžaduje.

    GUI spouští instalaci FFmpeg na pozadí (auto-install). Tady počkáme na
    její dokončení, aby yt-dlp (merge video+audio, MP3, titulky) i ořez měly
    FFmpeg k dispozici; hlavní vlákno UI se nikdy neblokuje. Když žádná
    instalace neběží a FFmpeg už je/není k dispozici, `wait_until_ready()`
    se vrátí okamžitě.

    Musí se zavolat PŘED sestavením yt-dlp opcí (`_build_ydl_opts`) – jen tak
    je `ffmpeg_location` platný, i když se FFmpeg stahuje na pozadí.
    """
    dl_mod.wait_until_ready()


def _build_ydl_opts(
    params: DownloadParams,
    config: dict,
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
        "concurrent_fragments": YTDLP_CONCURRENT_FRAGMENTS,
        "fragment_retries": YTDLP_FRAGMENT_RETRIES,
        "progress_hooks": [progress_hook],
        "socket_timeout": YTDLP_SOCKET_TIMEOUT,
        "retries": YTDLP_RETRIES,
        "extractor_retries": YTDLP_EXTRACTOR_RETRIES,
        "file_access_retries": YTDLP_FILE_ACCESS_RETRIES,
        "js_runtimes": {"node": {}},
    }

    cookies_opts = resolve_cookies_opts(config, url)
    opts.update(cookies_opts)
    opts.update(platform_opts(url))

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

    ffmpeg_bin = dl_mod.find_ffmpeg()
    if ffmpeg_bin is not None:
        opts["ffmpeg_location"] = str(ffmpeg_bin.parent)

    return opts


class YtDlpMixin:
    _cancel_event: threading.Event
    on_log: Callable[[str], None]
    on_status: Callable[[str, str, str], None]
    on_progress: Callable[[str, float, str, str], None]
    _cleanup_output: Callable[[dict], None]

    def _progress_hook(self, job_id: str, d: dict) -> None:
        if self._cancel_event.is_set():
            raise dl_mod.yt_dlp.utils.DownloadCancelled("Stahování zrušeno uživatelem")
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            percent = (downloaded / total * 100) if total > 0 else 0
            speed = _format_speed(d.get("speed"))
            eta = _format_eta(d.get("eta"))
            self.on_progress(job_id, percent, speed, eta)
        elif d["status"] == "finished":
            self.on_status(job_id, STATUS_FINISHED_PROCESSING, STATUS_ORANGE)

    def _download_with_ytdlp(self, url: str, opts: dict, job_id: str) -> bool:
        max_attempts = YTDLP_MAX_ATTEMPTS
        self.on_status(job_id, STATUS_DOWNLOADING, STATUS_BLUE)
        for attempt in range(1, max_attempts + 1):
            try:
                if self._cancel_event.is_set():
                    self._cleanup_output(opts)
                    return False
                ydl = dl_mod.yt_dlp.YoutubeDL(opts)
                ydl.download([url])
                return True
            except dl_mod.yt_dlp.utils.DownloadCancelled:
                self.on_log("Stahování zrušeno uživatelem")
                self._cleanup_output(opts)
                return False
            except dl_mod.yt_dlp.utils.DownloadError as e:
                err = str(e)
                if "zrušeno" in err.lower():
                    self._cleanup_output(opts)
                    return False
                if "Unable to download video subtitles" in err:
                    self.on_log(f"Titulky nebyly zcela staženy: {err[:200]}")
                    self.on_status(job_id, "Titulky staženy (některé jazyky nemusí být k dispozici).", STATUS_GREEN)
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
            except dl_mod.yt_dlp.utils.YoutubeDLError as ex:
                self.on_log(f"Chyba yt-dlp: {ex}")
                self.on_status(job_id, f"Chyba při stahování: {ex}", STATUS_ORANGE)
                self._cleanup_output(opts)
                return False
            except Exception as ex:
                self.on_log(f"Neočekávaná chyba: {ex}")
                self.on_status(job_id, "Neočekávaná chyba při stahování.", STATUS_ORANGE)
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
                STATUS_ORANGE,
            )
        elif "429" in err or "rate limit" in err.lower() or "http error 410" in err.lower():
            self.on_status(
                job_id,
                "Dočasné omezení ze strany serveru (příliš mnoho požadavků). Počkej chvíli a zkus to znovu.",
                STATUS_ORANGE,
            )
        elif "404" in err or "Video unavailable" in err or "not found (deleted or unavailable)" in err:
            self.on_status(job_id, "Video není dostupné nebo bylo smazáno.", STATUS_ORANGE)
        elif "registered users" in err:
            self.on_status(job_id, "Video vyžaduje přihlášení – použij cookies.", STATUS_ORANGE)
        else:
            self.on_status(job_id, f"Stahování selhalo: {err[:200]}", STATUS_ORANGE)


import stahovac.core.downloader as dl_mod  # noqa: E402  (cyklický import – jen runtime přístup)
