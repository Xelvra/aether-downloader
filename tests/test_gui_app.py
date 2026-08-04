import asyncio
import threading
from pathlib import Path

import flet as ft

import stahovac.gui.app as app_mod
from stahovac.config.constants import COOKIES_FILE_OPTION, CookieSource
from stahovac.gui.app import GuiApp
from stahovac.gui.theme import COLOR_SURFACE, COLOR_WARN


class _FakePage:
    def __init__(self):
        self.overlay = []
        self.drawer = None
        self.updates = 0
        self.width = 800
        self.height = 600
        self.closed_drawer = 0
        self.shown_drawer = 0

    def update(self):
        self.updates += 1

    async def close_drawer(self):
        self.closed_drawer += 1

    async def show_drawer(self):
        self.shown_drawer += 1


class _FakeBar:
    def __init__(self):
        self.visible = False
        self.value = None


class _FakeText:
    def __init__(self):
        self.value = ""
        self.color = None


class _FakeOverlay:
    def __init__(self):
        self.visible = False
        self.width = None
        self.height = None


class _FakeTabBar:
    def __init__(self):
        self.visible = True
        self.height = None


class _FakeControls:
    def __init__(self):
        self.controls = []


class _FakeContentArea:
    def __init__(self):
        self.content = None


class _FakeDownloadView:
    def __init__(self):
        self.downloading = False
        self.closed = False
        self.updated = []

    def set_downloading(self, value):
        self.downloading = value

    def close(self):
        self.closed = True

    def update_metadata_ui(self, meta):
        self.updated.append(meta)


class _FakeLogsView:
    def __init__(self):
        self.log_list_view = _FakeControls()
        self.rendered = 0

    def render_history(self):
        self.rendered += 1


class _FakeQualityView:
    def __init__(self):
        self.resolutions = []
        self.quality_dropdown = _FakeDropdown("Nejlepší dostupná")
        self.format_dropdown = _FakeDropdown("Video + audio (MP4)")
        self.re_encode_checkbox = _FakeCheckbox(False)
        self.crf_input = _FakeText()
        self.preset_dropdown = _FakeDropdown("fast")

    def update_qualities(self, res):
        self.resolutions.append(res)

    def to_params(self):
        return {
            "whole_video": True,
            "start_time": "00:00",
            "end_time": "00:00",
            "end_option": "Do konce videa",
            "re_encode": False,
            "crf": "23",
            "preset": "fast",
            "quality": "Nejlepší dostupná",
            "format_choice": "Video + audio (MP4)",
        }


class _FakeStorageView:
    def __init__(self):
        self.output_folder_text = _FakeText()
        self.cookies_dropdown = _FakeDropdown("Žádný (Bez cookies)")
        self.cookies_file_text = _FakeText()

    def set_ffmpeg_installing(self, *a):
        pass


class _FakeDropdown:
    def __init__(self, value=""):
        self.value = value


class _FakeCheckbox:
    def __init__(self, value=False):
        self.value = value


class _FakeState:
    def __init__(self):
        self.config = {}
        self.calls = []

    def update_config_from_ui(self, *args):
        self.calls.append(args)
        self.config["quality"] = args[0]


class _FakeManager:
    def __init__(self):
        self.state = _FakeState()
        self.save_result = True
        self.validate_error = None
        self.start_result = True
        self.started = None
        self.cancel_calls = 0

    def validate(self, params, *, crf_raw=None):
        return self.validate_error

    def start_download(self, params):
        self.started = params
        return self.start_result

    def config_save(self, config):
        return self.save_result

    def cancel_download(self):
        self.cancel_calls += 1


class _FfInstall:
    def __init__(self, installing=False):
        self.installing = installing


def _make_app(**overrides):
    app = GuiApp.__new__(GuiApp)
    statuses = []
    app._page = _FakePage()
    app._is_downloading = False
    app._active_tab = 0
    app._resize_bucket = (False, False)
    app._resize_timer = None
    app._unlock_timer = None
    app._pending_logs = []
    app._last_log_update = 0.0
    app._last_progress_update = 0.0
    app._ui_lock = threading.Lock()
    app._progress_bar = _FakeBar()
    app._status_text = _FakeText()
    app.logs_view = _FakeLogsView()
    app.download_view = _FakeDownloadView()
    app.quality_view = _FakeQualityView()
    app.storage_view = _FakeStorageView()
    app._manager = _FakeManager()
    app._config = {}
    app._help_overlay = _FakeOverlay()
    app._tab_bar = _FakeTabBar()
    app._tab_buttons_row = _FakeControls()
    app._tab_contents = [None, None, None, None]
    app._content_area = _FakeContentArea()
    app.ffmpeg_install = _FfInstall()
    app._safe_page_update = lambda: None
    app._run_ui_thread = lambda *a: None
    app.on_status = lambda text, color: statuses.append((text, color))
    for key, value in overrides.items():
        setattr(app, key, value)
    return app, statuses


class _FakeEvent:
    def __init__(self, data=None, selected_index=0, width=None):
        self.data = data
        self.control = _FakeControl(selected_index)
        self.width = width


class _FakeControl:
    def __init__(self, selected_index):
        self.selected_index = selected_index


class TestPageResize:
    def _reset_width(self, monkeypatch):
        import stahovac.gui.theme as theme

        captured = {}
        monkeypatch.setattr(theme, "set_screen_width", lambda w: captured.__setitem__("w", w))
        return captured

    def test_bucket_change_schedules_resize(self, monkeypatch):
        captured = self._reset_width(monkeypatch)
        app, _ = _make_app()
        app._resize_bucket = (False, False)
        app._resize_timer = None
        app._on_page_resized(_FakeEvent(data='{"width": 300}'))
        assert captured["w"] == 300
        assert app._resize_bucket == (True, True)
        assert app._resize_timer is not None
        app._resize_timer.cancel()

    def test_same_bucket_no_reschedule(self, monkeypatch):
        self._reset_width(monkeypatch)
        app, _ = _make_app()
        app._resize_bucket = (False, False)
        app._resize_timer = None
        app._on_page_resized(_FakeEvent(data='{"width": 800}'))
        assert app._resize_timer is None

    def test_invalid_width_falls_back_to_page_width(self, monkeypatch):
        captured = self._reset_width(monkeypatch)
        app, _ = _make_app()
        app._page.width = 500
        app._resize_bucket = (False, False)
        app._on_page_resized(_FakeEvent(data="nonsense"))
        assert captured["w"] == 500
        app._resize_timer.cancel()


class TestApplyResize:
    def test_rebuilds_active_tab_header_nav(self, monkeypatch):
        app, _ = _make_app()
        calls = []
        monkeypatch.setattr(app, "_rebuild_active_tab", lambda: calls.append("tab"))
        monkeypatch.setattr(app, "_rebuild_header", lambda: calls.append("header"))
        monkeypatch.setattr(app, "_rebuild_nav", lambda: calls.append("nav"))
        app._apply_resize()
        assert calls == ["tab", "header", "nav"]


class TestRebuildActiveTab:
    def test_uses_builder_for_active_index(self):
        app, _ = _make_app()
        app._active_tab = 2
        app._content_area = _FakeContentArea()
        app.download_view = _FakeBuild("d")
        app.quality_view = _FakeBuild("q")
        app.storage_view = _FakeBuild("s")
        app.logs_view = _FakeBuild("l")
        app._tab_contents = [None] * 4
        app._rebuild_active_tab()
        assert app._tab_contents[2] == "s"
        assert app._content_area.content == "s"


class _FakeBuild:
    def __init__(self, label):
        self._label = label

    def build(self):
        return self._label


class TestSafariCookiesBlocking:
    def test_non_darwin_returns_false(self, monkeypatch):
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Linux")
        app, statuses = _make_app()
        app._config = {"cookies_source": CookieSource.SAFARI.value}
        assert app._safari_cookies_blocking("https://kick.com/x") is False
        assert statuses == []

    def test_not_safari_source_returns_false(self, monkeypatch):
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Darwin")
        app, statuses = _make_app()
        app._config = {"cookies_source": "Chrome"}
        assert app._safari_cookies_blocking("https://kick.com/x") is False

    def test_youtube_returns_false(self, monkeypatch):
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Darwin")
        app, statuses = _make_app()
        app._config = {"cookies_source": CookieSource.SAFARI.value}
        assert app._safari_cookies_blocking("https://youtube.com/watch?v=x") is False

    def test_readable_returns_false(self, monkeypatch):
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(app_mod, "safari_cookies_readable", lambda: (True, ""))
        app, statuses = _make_app()
        app._config = {"cookies_source": CookieSource.SAFARI.value}
        assert app._safari_cookies_blocking("https://kick.com/x") is False

    def test_unreadable_blocks_and_unlocks(self, monkeypatch):
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(app_mod, "safari_cookies_readable", lambda: (False, "nelze přečíst"))
        app, statuses = _make_app()
        unlocked = []
        app._force_unlock_ui = lambda: unlocked.append(1)
        app._config = {"cookies_source": CookieSource.SAFARI.value}
        assert app._safari_cookies_blocking("https://kick.com/x") is True
        assert any("Safari" in t for t, _ in statuses)
        assert unlocked == [1]


class TestOnStartDownload:
    def test_exception_is_logged_and_unlocked(self, monkeypatch):
        app, statuses = _make_app()

        def boom(url):
            raise RuntimeError("boom")

        monkeypatch.setattr(app, "_start_download_impl", boom)
        logs = []
        monkeypatch.setattr(app, "_on_log_received", lambda t: logs.append(t))
        unlocked = []
        monkeypatch.setattr(app, "_force_unlock_ui", lambda: unlocked.append(1))
        app._on_start_download("https://x")
        assert any("CHYBA" in line for line in logs)
        assert any("Vnitřní chyba" in t for t, _ in statuses)
        assert unlocked == [1]


class TestStartDownloadImpl:
    def test_busy_reports_status(self, monkeypatch):
        app, statuses = _make_app()
        app._is_downloading = True
        app._start_download_impl("https://x")
        assert any("Stahování již probíhá" in t for t, _ in statuses)

    def test_empty_url_unlocks(self, monkeypatch):
        app, statuses = _make_app()
        unlocked = []
        monkeypatch.setattr(app, "_force_unlock_ui", lambda: unlocked.append(1))
        app._start_download_impl("")
        assert any("URL" in t for t, _ in statuses)
        assert unlocked == [1]

    def test_validation_error_blocks(self, monkeypatch):
        app, statuses = _make_app()
        app._manager.validate_error = "⚠️ Chyba"
        unlocked = []
        monkeypatch.setattr(app, "_force_unlock_ui", lambda: unlocked.append(1))
        started = []
        monkeypatch.setattr(app, "_do_start_download", lambda p: started.append(p))
        app._start_download_impl("https://youtu.be/x")
        assert started == []
        assert any("Chyba" in t for t, _ in statuses)
        assert unlocked == [1]

    def test_valid_starts(self, monkeypatch):
        app, statuses = _make_app()
        app.quality_view = _FakeQualityView()
        started = []
        monkeypatch.setattr(app, "_do_start_download", lambda p: started.append(p))
        app._start_download_impl("https://youtu.be/x")
        assert started


class TestDoStartDownload:
    def _patch_no_auto_install(self, monkeypatch):
        # Auto-instalace FFmpeg by volala controller.start() – testy ji mockují,
        # aby byly nezávislé na tom, jestli má CI/system ffmpeg nainstalovaný.
        monkeypatch.setattr(app_mod.ffmpeg, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))

    def test_manager_rejects_unlocks(self, monkeypatch):
        self._patch_no_auto_install(monkeypatch)
        app, statuses = _make_app()
        app._manager.start_result = False
        app._manager.started = None
        unlocked = []
        app._force_unlock_ui = lambda: unlocked.append(1)
        app._do_start_download(object())
        assert unlocked == [1]
        assert any("počkej" in t.lower() for t, _ in statuses)

    def test_sets_downloading_state(self, monkeypatch):
        self._patch_no_auto_install(monkeypatch)
        app, statuses = _make_app()
        app.ffmpeg_install = _FfInstall()
        app._do_start_download(object())
        assert app._is_downloading is True
        assert app.download_view.downloading is True
        assert app._progress_bar.visible is True


class TestOnSaveSettings:
    def _make(self):
        app, statuses = _make_app()
        app.quality_view = _FakeQualityView()
        app.storage_view = _FakeStorageView()
        app.storage_view.cookies_dropdown = _FakeDropdown(COOKIES_FILE_OPTION)
        app.storage_view.cookies_file_text = _FakeText()
        app.storage_view.cookies_file_text.value = "/tmp/cookies.txt"
        return app, statuses

    def test_invalid_cookies_file_aborts(self, monkeypatch):
        monkeypatch.setattr(app_mod, "validate_cookies_file", lambda p: "soubor neexistuje.")
        app, statuses = self._make()
        app._on_save_settings()
        assert any("Cookies" in t for t, _ in statuses)
        assert app._manager.state.calls == []

    def test_valid_saves_config(self, monkeypatch):
        monkeypatch.setattr(app_mod, "validate_cookies_file", lambda p: None)
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Linux")
        app, statuses = self._make()
        app._on_save_settings()
        assert app._manager.state.calls
        assert any("uložena" in t for t, _ in statuses)

    def test_save_failure_reports_warning(self, monkeypatch):
        monkeypatch.setattr(app_mod, "validate_cookies_file", lambda p: None)
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Linux")
        app, statuses = self._make()
        app._manager.save_result = False
        app._on_save_settings()
        assert any("Uložení se nezdařilo" in t for t, _ in statuses)

    def test_safari_unreadable_warns(self, monkeypatch):
        monkeypatch.setattr(app_mod, "validate_cookies_file", lambda p: None)
        monkeypatch.setattr(app_mod.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(app_mod, "safari_cookies_readable", lambda: (False, "nelze"))
        app, statuses = self._make()
        app.storage_view.cookies_dropdown = _FakeDropdown(CookieSource.SAFARI.value)
        app._on_save_settings()
        assert any("Safari cookies" in t for t, _ in statuses)
        assert app._manager.state.calls, "upozornění Safari jen varuje, uložení pokračuje"


class TestLogs:
    def test_append_logs_caps_at_500(self):
        app, _ = _make_app()
        app._pending_logs = [ft.Text("x")]
        app.logs_view.log_list_view.controls = [ft.Text("y") for _ in range(500)]
        app._append_logs()
        assert len(app.logs_view.log_list_view.controls) == 401

    def test_apply_log_strips_emoji_and_flushes(self, monkeypatch):
        monkeypatch.setattr(app_mod.time, "time", lambda: 100.0)
        app, _ = _make_app()
        app._last_log_update = 0.0
        app._apply_log("✅ text")
        assert app._pending_logs == []
        assert app.logs_view.log_list_view.controls[0].value == "text"

    def test_apply_log_throttled(self, monkeypatch):
        monkeypatch.setattr(app_mod.time, "time", lambda: 100.0)
        app, _ = _make_app()
        app._last_log_update = 99.9
        app._apply_log("zpráva")
        assert len(app._pending_logs) == 1
        assert app.logs_view.log_list_view.controls == []


class TestProgressAndStatus:
    def test_progress_applied(self, monkeypatch):
        monkeypatch.setattr(app_mod.time, "time", lambda: 100.0)
        app, _ = _make_app()
        app._last_progress_update = 0.0
        app._apply_progress(50.0, "2 MB/s", "1m")
        assert app._progress_bar.value == 0.5
        assert "50.0%" in app._status_text.value

    def test_progress_skipped_while_ffmpeg_installing(self, monkeypatch):
        monkeypatch.setattr(app_mod.time, "time", lambda: 100.0)
        app, _ = _make_app()
        app.ffmpeg_install = _FfInstall(installing=True)
        app._apply_progress(50.0, "2 MB/s", "1m")
        assert app._progress_bar.value is None

    def test_status_skipped_while_ffmpeg_installing(self, monkeypatch):
        app, _ = _make_app()
        app.ffmpeg_install = _FfInstall(installing=True)
        app._apply_status("text", "blue")
        assert app._status_text.value == ""

    def test_status_applied(self):
        app, _ = _make_app()
        app._apply_status("text", COLOR_WARN)
        assert app._status_text.value == "text"
        assert app._status_text.color == COLOR_WARN


class TestForceUnlock:
    def test_cancels_timer_and_resets(self):
        app, _ = _make_app()
        app._is_downloading = True
        app._unlock_timer = threading.Timer(60, lambda: None)
        app._progress_bar.visible = True
        app.download_view.downloading = True
        app._force_unlock_ui()
        assert app._is_downloading is False
        assert app._progress_bar.visible is False
        assert app.download_view.downloading is False
        assert app._unlock_timer is None


class TestTabs:
    def test_update_tab_bar_builds_four_buttons(self):
        app, _ = _make_app()
        app._update_tab_bar()
        assert len(app._tab_buttons_row.controls) == 4

    def test_apply_tab_states_marks_active(self):
        app, _ = _make_app()
        app._active_tab = 2
        app._update_tab_bar()
        app._apply_tab_states()
        assert app._tab_buttons_row.controls[2].bgcolor == COLOR_SURFACE
        assert app._tab_buttons_row.controls[0].bgcolor is None

    def test_switch_tab_renders_history_for_index_3(self, monkeypatch):
        app, _ = _make_app()
        app.logs_view.render_history = lambda: setattr(app.logs_view, "rendered", app.logs_view.rendered + 1)
        monkeypatch.setattr(app, "_rebuild_active_tab", lambda: None)
        app._switch_tab(3)
        assert app._active_tab == 3
        assert app.logs_view.rendered == 1

    def test_make_tab_button_active(self):
        app, _ = _make_app()
        app._active_tab = 1
        button = app._make_tab_button("Ořez", ft.Icons.CUT_ROUNDED, 1)
        assert button.bgcolor == COLOR_SURFACE


class TestHelpOverlay:
    def test_show_help_makes_visible(self):
        app, _ = _make_app()
        app._help_overlay = _FakeOverlay()
        app._show_help()
        assert app._help_overlay.visible is True
        assert app._page.updates == 1

    def test_close_help_hides(self):
        app, _ = _make_app()
        app._help_overlay = _FakeOverlay()
        app._help_overlay.visible = True
        app._close_help()
        assert app._help_overlay.visible is False


class TestDrawer:
    def test_open_drawer_shows(self):
        app, _ = _make_app()
        asyncio.run(app._open_drawer())
        assert app._page.shown_drawer == 1

    def test_drawer_change_help_index(self):
        app, _ = _make_app()
        app._help_overlay = _FakeOverlay()
        asyncio.run(app._on_drawer_change(_FakeEvent(selected_index=4)))
        assert app._page.closed_drawer == 1
        assert app._help_overlay.visible is True

    def test_drawer_change_switches_tab(self, monkeypatch):
        app, _ = _make_app()
        app.logs_view.render_history = lambda: setattr(app.logs_view, "rendered", app.logs_view.rendered + 1)
        monkeypatch.setattr(app, "_rebuild_active_tab", lambda: None)
        asyncio.run(app._on_drawer_change(_FakeEvent(selected_index=3)))
        assert app._active_tab == 3
        assert app.logs_view.rendered == 1
        assert app._page.closed_drawer == 1


class TestApplyMeta:
    def test_updates_views(self):
        app, _ = _make_app()

        class _Meta:
            available_resolutions = [1080, 720]

        meta = _Meta()
        app._apply_meta(meta)
        assert app.download_view.updated == [meta]
        assert app.quality_view.resolutions == [[1080, 720]]

    def test_no_resolutions_skips_quality(self):
        app, _ = _make_app()

        class _Meta:
            available_resolutions = []

        app._apply_meta(_Meta())
        assert app.quality_view.resolutions == []
