"""Controller instalace FFmpeg na pozadí (vydělený z `GuiApp`).

Audit §6.2 – FFmpeg-install flow žil v `GuiApp` (7 metod: start, progress,
done, failed). `FfmpegInstallController` tento flow zapouzdřuje; `GuiApp`
jen deleguje přes `self.ffmpeg_install.start(...)` a čte
`self.ffmpeg_install.installing`.

Host (GuiApp) musí vystavovat: `run_ui_thread`, `safe_page_update`,
`storage_view`, `progress_bar`, `status_text`, `ui_lock` a `is_downloading`.
"""

import threading
import time

from stahovac.core import ffmpeg
from stahovac.gui.theme import COLOR_SUCCESS, COLOR_WARN


class FfmpegInstallController:
    def __init__(self, ui):
        self._ui = ui
        self._installing = False
        self._last_progress = 0.0

    @property
    def installing(self) -> bool:
        return self._installing

    def start(self, auto: bool = False) -> None:
        """Spustí instalaci FFmpeg na pozadí.

        ``auto=True`` – volá se automaticky při prvním ořezu/MP3 (bez zásahu
        uživatele). Průběh běží ve společném progress pruhu jako stahování.
        """
        if self._installing:
            return
        if not ffmpeg.claim_install():
            self._installing = True
            return
        self._installing = True
        self._last_progress = 0.0
        self._set_progress(None)
        self._ui.run_ui_thread(self._ui.storage_view.set_ffmpeg_installing, True, "Stahuji FFmpeg…")
        threading.Thread(target=self._worker, daemon=True).start()
        self._ui.safe_page_update()

    def _set_progress(self, percent: float | None) -> None:
        self._ui.progress_bar.visible = True
        self._ui.progress_bar.value = percent / 100.0 if percent is not None else None
        self._ui.status_text.value = "Stahuji FFmpeg…"
        self._ui.status_text.color = COLOR_WARN

    def _worker(self) -> None:
        def progress(percent, speed, eta):
            self._ui.run_ui_thread(self._apply_progress, percent, speed, eta)

        try:
            installed = ffmpeg.run_install(progress_cb=progress)
        except Exception as ex:
            self._ui.run_ui_thread(self._apply_install_failed, str(ex))
        else:
            self._ui.run_ui_thread(self._apply_install_done, installed is not None)

    def _apply_progress(self, percent, speed, eta) -> None:
        with self._ui.ui_lock:
            now = time.time()
            if now - self._last_progress < 0.15:
                return
            self._last_progress = now
            text = f"Stahuji FFmpeg… {percent:.1f}%  \u2022  {speed}  \u2022  Zbývá: {eta}"
            self._ui.progress_bar.visible = True
            self._ui.progress_bar.value = percent / 100.0
            self._ui.status_text.value = text
            self._ui.status_text.color = COLOR_WARN
            self._ui.safe_page_update()

    def _apply_install_done(self, ok: bool) -> None:
        with self._ui.ui_lock:
            self._installing = False
            self._ui.storage_view.set_ffmpeg_installing(False)
            if ok:
                self._ui.status_text.value = "FFmpeg připraven."
                self._ui.status_text.color = COLOR_SUCCESS
            else:
                self._ui.status_text.value = "FFmpeg se nepodařilo nainstalovat. Zkus to v Nastavení."
                self._ui.status_text.color = COLOR_WARN
            if not self._ui.is_downloading:
                self._ui.progress_bar.visible = False
            else:
                self._ui.progress_bar.value = None
            self._ui.safe_page_update()

    def _apply_install_failed(self, error: str) -> None:
        with self._ui.ui_lock:
            self._installing = False
            self._ui.storage_view.set_ffmpeg_installing(False)
            self._ui.status_text.value = f"FFmpeg se nepodařilo nainstalovat ({error}). Návod najdeš v nápovědě."
            self._ui.status_text.color = COLOR_WARN
            if not self._ui.is_downloading:
                self._ui.progress_bar.visible = False
            self._ui.safe_page_update()
