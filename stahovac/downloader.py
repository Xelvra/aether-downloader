import uuid
from collections.abc import Callable
from typing import Any

from stahovac.config.manager import ConfigManager
from stahovac.core.downloader import Downloader
from stahovac.core.validator import validate_download_params
from stahovac.models import DownloadParams, DownloadState
from stahovac.state import AppState


class DownloadManager:
    """Fasáda mezi GUI a `Downloader`.

    Vlastní jediný zdroj pravdy o životním cyklu stahování
    (`download_state`) a identitu aktivní úlohy (`active_job_id`).
    Callbacky z vláken staré úlohy (job_id != aktivní) jsou odfiltrovány,
    takže starý worker nemůže přepsat stav nového stahování.

    Stavový model: `FINISHED`/`FAILED` jsou terminální stavy. Nová úloha
    se přijímá kdykoli, kdy `is_busy()` je False; `start_download()`
    přejde z jakéhokoli stavu přímo na `DOWNLOADING`.
    """

    def __init__(
        self,
        on_log: Callable[[str], None] | None = None,
        on_progress: Callable[[str, float, str, str], None] | None = None,
        on_status: Callable[[str, str, str], None] | None = None,
        on_finish: Callable[[str, bool, str], None] | None = None,
    ):
        self.state = AppState(ConfigManager.load())
        self._downloader = Downloader(self.state.config)
        self._active_job_id: str | None = None
        self._download_state = DownloadState.IDLE

        self._user_callbacks: dict[str, Callable[..., None]] = {
            "on_log": on_log or (lambda text: None),
            "on_progress": on_progress or (lambda job_id, percent, speed, eta: None),
            "on_status": on_status or (lambda job_id, text, color: None),
            "on_finish": on_finish or (lambda job_id, success, message: None),
        }

        self._downloader.on_log = self._user_callbacks["on_log"]
        self._downloader.on_progress = self._wrap_progress
        self._downloader.on_status = self._wrap_status
        self._downloader.on_finish = self._wrap_finish
        self._downloader.on_state = self._wrap_state

    @property
    def downloader(self) -> Downloader:
        return self._downloader

    @property
    def download_state(self) -> DownloadState:
        return self._download_state

    @property
    def active_job_id(self) -> str | None:
        return self._active_job_id

    def is_busy(self) -> bool:
        return self._downloader.is_busy()

    def validate(self, params: DownloadParams, *, crf_raw: str | None = None) -> str | None:
        """Ověří požadavek na stahování (URL, ořez, CRF) – viz core/validator.

        Vrací uživatelsky srozumitelnou chybovou hlášku, nebo ``None``.
        Volá se před ``start_download()`` z libovolného vstupního bodu
        (GUI dnes, případně CLI později), takže validace nežije v GUI vrstvě.
        """
        return validate_download_params(params, crf_raw=crf_raw)

    def _is_active(self, job_id: str) -> bool:
        return not job_id or job_id == self._active_job_id

    def _wrap_progress(self, job_id: str, percent: float, speed: str, eta: str) -> None:
        if self._is_active(job_id):
            self._user_callbacks["on_progress"](job_id, percent, speed, eta)

    def _wrap_status(self, job_id: str, text: str, color: str) -> None:
        if self._is_active(job_id):
            self._user_callbacks["on_status"](job_id, text, color)

    def _wrap_finish(self, job_id: str, success: bool, message: str) -> None:
        if self._is_active(job_id):
            self._active_job_id = None
            if self._download_state != DownloadState.CANCELLED:
                self._download_state = DownloadState.FINISHED if success else DownloadState.FAILED
            self._user_callbacks["on_finish"](job_id, success, message)

    def _wrap_state(self, state: DownloadState) -> None:
        self._download_state = state

    def start_download(self, params: DownloadParams) -> bool:
        if self._downloader.is_busy():
            return False
        job_id = uuid.uuid4().hex
        self._active_job_id = job_id
        self._download_state = DownloadState.DOWNLOADING
        if not self._downloader.start(params, job_id=job_id):
            self._active_job_id = None
            self._download_state = DownloadState.IDLE
            return False
        return True

    def cancel_download(self) -> None:
        if self._download_state not in (DownloadState.IDLE, DownloadState.FINISHED, DownloadState.FAILED):
            self._download_state = DownloadState.CANCELLING
        self._downloader.cancel()

    def config_save(self, config_data: dict[str, Any]) -> bool:
        return ConfigManager.save(config_data)
