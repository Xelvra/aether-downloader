import time

from stahovac.config.constants import COOKIES_FILE_OPTION, COOKIES_NONE
from stahovac.gui.storage_view import StorageView


class _FakePage:
    def __init__(self):
        self.overlay = []
        self.width = 800
        self.height = 600
        self.updates = 0

    def update(self):
        self.updates += 1


class _State:
    def __init__(self, config=None):
        self.config = config or {}


class _FakePicker:
    def __init__(self):
        self.calls = []

    def open(self, mode="folder", initial_dir=None):
        self.calls.append((mode, initial_dir))


def _make(state=None, on_save=None, monkeypatch=None, ffmpeg_version=None):
    saved = []
    page = _FakePage()
    if monkeypatch is not None:
        import stahovac.gui.storage_view as sv

        monkeypatch.setattr(sv, "get_ffmpeg_version", lambda: ffmpeg_version)
    view = StorageView(page, state or _State(), on_save_callback=on_save or (lambda: saved.append(1)))
    return view, page, saved


class TestInit:
    def test_picker_mode_defaults_to_folder(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        assert view._picker_mode == "folder"


class TestOnPickerResult:
    def test_folder_updates_output_folder_and_saves(self, tmp_path, monkeypatch):
        view, _, saved = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view._picker_mode = "folder"
        target = tmp_path / "slozka"
        target.mkdir()
        view._on_picker_result(str(target))
        assert view._state.config["output_folder"] == str(target.resolve())
        assert view.output_folder_text.value == str(target.resolve())
        assert saved == [1]

    def test_file_updates_cookies_path_and_saves(self, tmp_path, monkeypatch):
        view, _, saved = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view._picker_mode = "file"
        target = tmp_path / "cookies.txt"
        target.write_text("x")
        view._on_picker_result(str(target))
        assert view._state.config["cookies_file_path"] == str(target.resolve())
        assert view.cookies_file_text.value == str(target.resolve())
        assert saved == [1]

    def test_none_is_noop(self, monkeypatch):
        view, _, saved = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view._picker_mode = "folder"
        view._on_picker_result(None)
        assert "output_folder" not in view._state.config
        assert saved == []


class TestPickFolder:
    def test_debounce_blocks_rapid_second_call(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view._file_picker = _FakePicker()
        view._last_dialog_time = time.time()
        view._pick_folder(None)
        assert view._file_picker.calls == []

    def test_sets_mode_and_opens_picker(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view._file_picker = _FakePicker()
        view._last_dialog_time = 0.0
        view._pick_folder(None)
        assert view._picker_mode == "folder"
        assert view._file_picker.calls == [("folder", view.output_folder_text.value)]

    def test_select_cookies_file_sets_file_mode(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view._file_picker = _FakePicker()
        view._last_dialog_time = 0.0
        view._select_cookies_file(None)
        assert view._picker_mode == "file"
        assert view._file_picker.calls[0][0] == "file"


class TestRefreshFfmpegStatus:
    def test_installed(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version="7.1")
        view.refresh_ffmpeg_status()
        assert "nainstalováno" in view.ffmpeg_status_text.value
        assert view.ffmpeg_install_btn.content == "Přeinstalovat FFmpeg"

    def test_not_installed(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view.refresh_ffmpeg_status()
        assert "nenainstalováno" in view.ffmpeg_status_text.value
        assert view.ffmpeg_install_btn.content == "Stáhnout FFmpeg"


class TestSetFfmpegInstalling:
    def test_installing_hides_button(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view.set_ffmpeg_installing(True, "Stahuji FFmpeg…")
        assert view._ffmpeg_installing is True
        assert view.ffmpeg_install_btn.visible is False
        assert view.ffmpeg_status_text.value == "Stahuji FFmpeg…"

    def test_done_refreshes_status(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version="7.1")
        refreshed = []
        monkeypatch.setattr(view, "refresh_ffmpeg_status", lambda: refreshed.append(1))
        view.set_ffmpeg_installing(False)
        assert view._ffmpeg_installing is False
        assert refreshed == [1]


class TestHandleCookiesSourceChange:
    def test_file_option_shows_file_row(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view.cookies_dropdown.value = COOKIES_FILE_OPTION
        view._handle_cookies_source_change(None)
        assert view.cookies_file_row.visible is True

    def test_other_option_hides_file_row(self, monkeypatch):
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view.cookies_dropdown.value = COOKIES_NONE
        view._handle_cookies_source_change(None)
        assert view.cookies_file_row.visible is False


class TestOpenOutputFolder:
    def test_failure_notifies(self, monkeypatch):
        import stahovac.gui.storage_view as sv

        monkeypatch.setattr(sv, "open_path", lambda p: (False, "chyba"))
        notified = []
        monkeypatch.setattr(sv.th, "notify", lambda page, m: notified.append(m))
        view, _, _ = _make(monkeypatch=monkeypatch, ffmpeg_version=None)
        view._open_output_folder(None)
        assert notified == ["chyba"]
