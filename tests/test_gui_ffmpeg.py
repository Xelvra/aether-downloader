import threading
from pathlib import Path

from stahovac.gui.app import GuiApp
from stahovac.gui.ffmpeg_install import FfmpegInstallController
from stahovac.models import DownloadParams


class _FakeManager:
    def __init__(self):
        self.started = []

    def start_download(self, params):
        self.started.append(params)
        return True


class _FakeDownloadView:
    def set_downloading(self, value):
        pass


class _FakeLogsView:
    def __init__(self):
        self.log_list_view = _FakeControls()


class _FakeControls:
    def __init__(self):
        self.controls = []


class _FakeBar:
    def __init__(self):
        self.visible = False
        self.value = None


class _FakeText:
    def __init__(self):
        self.value = ""
        self.color = None


class _FakeStorageView:
    def set_ffmpeg_installing(self, *args, **kwargs):
        pass


def _make_app():
    app = GuiApp.__new__(GuiApp)
    app._pending_download = None
    app._is_downloading = False
    app._manager = _FakeManager()
    app._progress_bar = _FakeBar()
    app._status_text = _FakeText()
    app._last_log_update = 0.0
    app._last_progress_update = 0.0
    app._ui_lock = threading.Lock()
    app.download_view = _FakeDownloadView()
    app.logs_view = _FakeLogsView()
    app.storage_view = _FakeStorageView()
    app.ffmpeg_install = FfmpegInstallController(app)
    app._safe_page_update = lambda: None
    app.on_status = lambda *a: None
    app._run_ui_thread = lambda *a: None
    return app


class TestAutoFfmpegInstall:
    def test_auto_install_triggered_for_trim(self, monkeypatch):
        app = _make_app()
        started = []
        monkeypatch.setattr("stahovac.gui.app.ffmpeg.find_ffmpeg", lambda: None)
        app._start_ffmpeg_install = lambda auto=False: started.append(auto)
        params = DownloadParams(url="https://x", whole_video=False)
        app._do_start_download(params)
        assert started == [True]
        assert app._manager.started == [params]

    def test_auto_install_triggered_for_whole_video_mp4(self, monkeypatch):
        """Merge video+audio (bestvideo+bestaudio) vyžaduje FFmpeg i bez ořezu."""
        app = _make_app()
        started = []
        monkeypatch.setattr("stahovac.gui.app.ffmpeg.find_ffmpeg", lambda: None)
        app._start_ffmpeg_install = lambda auto=False: started.append(auto)
        params = DownloadParams(url="https://x", whole_video=True)
        app._do_start_download(params)
        assert started == [True]
        assert app._manager.started == [params]

    def test_auto_install_skipped_when_ffmpeg_present(self, monkeypatch):
        app = _make_app()
        started = []
        monkeypatch.setattr("stahovac.gui.app.ffmpeg.find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))
        app._start_ffmpeg_install = lambda auto=False: started.append(auto)
        params = DownloadParams(url="https://x", whole_video=False)
        app._do_start_download(params)
        assert started == []
        assert app._manager.started == [params]

    def test_real_auto_install_does_not_crash(self, monkeypatch):
        """Regrese: FfmpegInstallController čte host atributy privátními názvy.

        Kdyby controller použil veřejné názvy (`progress_bar`, `status_text`,
        ...), auto-instalace FFmpeg by hodila
        `AttributeError: 'GuiApp' object has no attribute 'progress_bar'`.
        """
        from stahovac.core import ffmpeg

        app = _make_app()
        monkeypatch.setattr("stahovac.gui.app.ffmpeg.find_ffmpeg", lambda: None)
        monkeypatch.setattr(ffmpeg, "claim_install", lambda: True)
        monkeypatch.setattr(ffmpeg, "run_install", lambda progress_cb=None, cancel_check=None: None)
        params = DownloadParams(url="https://x", whole_video=False)
        app._do_start_download(params)
        assert app.ffmpeg_install.installing is True
        assert app._manager.started == [params]
