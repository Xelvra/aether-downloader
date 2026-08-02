import threading

from stahovac.gui.app import GuiApp
from stahovac.gui.theme import COLOR_WARN


class _FakePage:
    def __init__(self):
        self.unlocked = []

    def run_thread(self, handler, *args):
        handler(*args)


class _FakeDownloader:
    def __init__(self):
        self.force_stop_calls = 0

    def force_stop(self):
        self.force_stop_calls += 1


class _FakeManager:
    def __init__(self):
        self.downloader = _FakeDownloader()
        self.cancel_calls = 0

    def cancel_download(self):
        self.cancel_calls += 1


class _FakeBar:
    def __init__(self):
        self.visible = True
        self.value = None


class _FakeDownloadView:
    def __init__(self):
        self.downloading = True
        self.closed = False

    def set_downloading(self, value):
        self.downloading = value

    def close(self):
        self.closed = True


def _make_app():
    app = GuiApp.__new__(GuiApp)
    app._is_downloading = True
    app._manager = _FakeManager()
    app._unlock_timer = None
    app._resize_timer = None
    app._page = _FakePage()
    app._pending_download = object()
    app._ui_lock = threading.Lock()
    statuses = []
    app.on_status = lambda text, color: statuses.append((text, color))
    app._progress_bar = _FakeBar()
    app.download_view = _FakeDownloadView()

    class _FakeLogsView:
        def __init__(self):
            self.rendered = 0

        def render_history(self):
            self.rendered += 1

    app.logs_view = _FakeLogsView()
    app._safe_page_update = lambda: None
    return app, statuses


def _cancel_timer(app):
    if app._unlock_timer:
        app._unlock_timer.cancel()
        app._unlock_timer = None


class TestCancelDownload:
    def test_cancel_requests_and_schedules_force_stop(self):
        app, statuses = _make_app()
        app._on_cancel_download()
        assert app._manager.cancel_calls == 1
        assert statuses == [("Ruším stahování…", COLOR_WARN)]
        assert app._unlock_timer is not None
        _cancel_timer(app)

    def test_cancel_when_idle_does_nothing(self):
        app, statuses = _make_app()
        app._is_downloading = False
        app._on_cancel_download()
        assert app._manager.cancel_calls == 0
        assert statuses == []
        assert app._unlock_timer is None

    def test_force_stop_stage_calls_downloader(self):
        app, statuses = _make_app()
        app._force_stop_stage()
        assert app._manager.downloader.force_stop_calls == 1
        assert any("vynucuji zastavení" in t for t, _ in statuses)
        _cancel_timer(app)

    def test_force_stop_stage_skips_when_idle(self):
        app, statuses = _make_app()
        app._is_downloading = False
        app._force_stop_stage()
        assert app._manager.downloader.force_stop_calls == 0
        assert statuses == []
        assert app._unlock_timer is None

    def test_force_unlock_stage_unlocks_ui(self):
        app, statuses = _make_app()
        app._force_unlock_stage()
        assert app._is_downloading is False
        assert app._progress_bar.visible is False
        assert app.download_view.downloading is False
        assert any("násilně ukončeno" in t for t, _ in statuses)

    def test_force_unlock_stage_skips_when_already_idle(self):
        app, statuses = _make_app()
        app._is_downloading = False
        app._force_unlock_stage()
        assert statuses == []


class TestUiSafety:
    def test_safe_page_update_suppresses_errors(self):
        app, _ = _make_app()

        class BadPage:
            def update(self):
                raise RuntimeError("boom")

        app._page = BadPage()
        app._safe_page_update()

    def test_run_ui_thread_suppresses_errors(self):
        app, _ = _make_app()

        class BadPage:
            def run_thread(self, handler, *args):
                raise RuntimeError("boom")

        app._page = BadPage()
        app._run_ui_thread(lambda: None)

    def test_apply_finish_unlocks_and_renders_history(self):
        app, _ = _make_app()
        app._unlock_timer = threading.Timer(60, lambda: None)
        app._apply_finish(True, "Úspěch")
        assert app._is_downloading is False
        assert app._unlock_timer is None
        assert app.logs_view.rendered == 1

    def test_apply_finish_failure_does_not_render_history(self):
        app, _ = _make_app()
        app._apply_finish(False, "Stahování selhalo")
        assert app._is_downloading is False
        assert app.logs_view.rendered == 0


class TestPageClose:
    def test_close_cancels_and_force_stops(self):
        app, _ = _make_app()
        app._unlock_timer = threading.Timer(60, lambda: None)
        app._resize_timer = threading.Timer(60, lambda: None)
        app._on_page_close()
        assert app._manager.cancel_calls == 1
        assert app._manager.downloader.force_stop_calls == 1
        assert app.download_view.closed is True
        assert app._unlock_timer is None
        assert app._resize_timer is None

    def test_close_when_idle_does_not_touch_downloader(self):
        app, _ = _make_app()
        app._is_downloading = False
        app._on_page_close()
        assert app._manager.cancel_calls == 0
        assert app._manager.downloader.force_stop_calls == 0
        assert app.download_view.closed is True
