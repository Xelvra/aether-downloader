import threading
import time
from pathlib import Path

from stahovac.gui import ffmpeg_install as ffi_mod
from stahovac.gui.ffmpeg_install import FfmpegInstallController


class _Bar:
    def __init__(self):
        self.visible = False
        self.value = None


class _Text:
    def __init__(self):
        self.value = ""
        self.color = None


class _StorageView:
    def __init__(self):
        self.calls = []

    def set_ffmpeg_installing(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class _Ui:
    """Napodobuje reálný `GuiApp` – host atributy jsou privátní."""

    def __init__(self):
        self.storage_view = _StorageView()
        self._progress_bar = _Bar()
        self._status_text = _Text()
        self._ui_lock = threading.Lock()
        self._is_downloading = False
        self._safe_page_update = lambda: None

    def _run_ui_thread(self, handler, *args):
        return handler(*args)


class _CapturingThread:
    """Zachytí vlákno, aniž by ho skutečně spustil."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        pass


def _make(monkeypatch):
    monkeypatch.setattr(ffi_mod.threading, "Thread", _CapturingThread)
    return FfmpegInstallController(_Ui())


class TestFfmpegInstallController:
    def test_start_claims_and_prepares_ui(self, monkeypatch):
        from stahovac.core import ffmpeg

        monkeypatch.setattr(ffmpeg, "claim_install", lambda: True)
        ctrl = _make(monkeypatch)
        ctrl.start(auto=True)
        assert ctrl.installing is True
        assert ctrl._ui.storage_view.calls, "set_ffmpeg_installing mělo být zavoláno"
        assert ctrl._ui.storage_view.calls[0][0][0] is True
        assert ctrl._ui._progress_bar.visible is True

    def test_start_noop_when_already_installing(self, monkeypatch):
        from stahovac.core import ffmpeg

        monkeypatch.setattr(ffmpeg, "claim_install", lambda: True)
        ctrl = _make(monkeypatch)
        ctrl.start()
        ui = ctrl._ui
        ui.storage_view.calls.clear()
        ctrl.start()
        assert len(ui.storage_view.calls) == 0

    def test_start_marks_installing_when_claim_rejected(self, monkeypatch):
        from stahovac.core import ffmpeg

        monkeypatch.setattr(ffmpeg, "claim_install", lambda: False)
        ctrl = _make(monkeypatch)
        ctrl.start()
        assert ctrl.installing is True
        assert ctrl._ui.storage_view.calls == []

    def test_worker_reports_done(self, monkeypatch):
        from stahovac.core import ffmpeg

        monkeypatch.setattr(ffmpeg, "run_install", lambda progress_cb=None, cancel_check=None: Path("/x/ffmpeg"))
        ctrl = _make(monkeypatch)
        ctrl._installing = True
        ctrl._worker()
        assert ctrl.installing is False
        assert ctrl._ui._status_text.value == "FFmpeg připraven."
        assert ctrl._ui._progress_bar.visible is False

    def test_worker_reports_failure(self, monkeypatch):
        from stahovac.core import ffmpeg

        def boom(progress_cb=None, cancel_check=None):
            raise RuntimeError("net down")

        monkeypatch.setattr(ffmpeg, "run_install", boom)
        ctrl = _make(monkeypatch)
        ctrl._installing = True
        ctrl._worker()
        assert ctrl.installing is False
        assert "net down" in ctrl._ui._status_text.value

    def test_progress_throttled_and_applied(self, monkeypatch):
        ctrl = _make(monkeypatch)
        ctrl._last_progress = time.time()
        ctrl._apply_progress(50, "1MiB/s", "00:10")
        assert ctrl._ui._progress_bar.value is None  # zthrottled → beze změny

        ctrl._last_progress = 0.0
        ctrl._apply_progress(50, "1MiB/s", "00:10")
        assert ctrl._ui._progress_bar.value == 0.5
        assert "50.0%" in ctrl._ui._status_text.value
