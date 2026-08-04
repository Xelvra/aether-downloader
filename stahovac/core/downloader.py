import os  # noqa: F401  (monkeypatch target v testech: dl_mod.os)
import platform  # noqa: F401  (monkeypatch target v testech: dl_mod.platform)
import shutil
import signal  # noqa: F401  (monkeypatch target v testech: dl_mod.signal)
import subprocess  # noqa: F401  (monkeypatch target v testech: dl_mod.subprocess)
import threading
import time  # noqa: F401  (monkeypatch target v testech: dl_mod.time)
import traceback
import uuid
from pathlib import Path
from typing import Any

import yt_dlp

from stahovac.config.app_config import coerce_crf
from stahovac.config.constants import FORMAT_MP4, MediaFormat
from stahovac.core._ffmpeg import (  # noqa: F401  (re-export: zůstává importovatelné z core.downloader)
    _RE_FFMPEG_TIME,
    FfmpegTrimMixin,
    _build_ffmpeg_cmd,
    _build_ranged_cmd,
    _estimate_cut_duration,
    _ffmpeg_timeout,
    _fmt_timestamp,
    _headers_args,
    _hls_input_args,
)
from stahovac.core._hls_ranged import (  # noqa: F401  (re-export)
    HlsRangedMixin,
    _can_ranged_hls,
    _closest_height_format,
    _ranged_output_name,
    _select_hls_formats,
)
from stahovac.core._process import (  # noqa: F401  (re-export: monkeypatch targety i přímé importy testů)
    _CHILD_PROCESSES,
    _CHILD_PROCESSES_LOCK,
    _cleanup_child_processes,
    _find_job_file,
    _kill_process,
    _sanitize_cmd,
    _track_process,
    _unique_dest,
    _untrack_process,
)
from stahovac.core._ytdlp import YtDlpMixin, _build_ydl_opts, _ensure_ffmpeg_ready
from stahovac.core.ffmpeg import find_ffmpeg, wait_until_ready  # noqa: F401  (monkeypatch targety)
from stahovac.core.metadata import MetadataService
from stahovac.models import DownloadParams, DownloadState
from stahovac.platforms import platform_opts
from stahovac.storage.history import HistoryManager
from stahovac.utils.format import format_eta as _format_eta  # noqa: F401  (re-export pro testy)
from stahovac.utils.format import format_speed as _format_speed  # noqa: F401  (re-export pro testy)

JOBS_DIR_NAME = ".jobs"
AETHER_KEEP_FAILED_JOBS = "AETHER_KEEP_FAILED_JOBS"


class Downloader(YtDlpMixin, HlsRangedMixin):
    """Orchestrátor stahování – tenká fasáda nad rozdělenými odpovědnostmi.

    Odpovědnosti (audit §6.1):
    - `YtDlpMixin` (`core/_ytdlp.py`) – yt-dlp opce, retry, klasifikace chyb,
    - `FfmpegTrimMixin` (`core/_ffmpeg.py`) – ořez a sledování FFmpeg procesu,
    - `HlsRangedMixin` (`core/_hls_ranged.py`) – ranged stahování z HLS,
    - tento soubor – životní cyklus úlohy (worker state machine), přesun
      výstupních souborů, finish/cancel reportování.
    """

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
            _ensure_ffmpeg_ready(params)
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
                        _ensure_ffmpeg_ready(params)
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
        return coerce_crf(value)

    @staticmethod
    def _platform_opts(url: str) -> dict:
        return platform_opts(url)

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
