from pathlib import Path

import pytest

from stahovac.gui.custom_file_picker import CustomFilePicker


class _FakePage:
    def __init__(self, width=800, height=600):
        self.overlay = []
        self.width = width
        self.height = height

    def update(self):
        pass

    def run_thread(self, handler, *args):
        handler(*args)


@pytest.fixture
def picker(monkeypatch):
    monkeypatch.setattr(CustomFilePicker, "_load_entries", lambda self: None)
    results = []
    page = _FakePage()
    picker = CustomFilePicker(page, on_result=results.append)
    picker._results = results
    return picker


class TestSelectButtonState:
    def test_file_mode_disabled_until_selection(self, picker, tmp_path):
        picker.open(mode="file", initial_dir=tmp_path)
        assert picker._select_btn.disabled is True

    def test_folder_mode_always_enabled(self, picker, tmp_path):
        picker.open(mode="folder", initial_dir=tmp_path)
        assert picker._select_btn.disabled is False

    def test_selecting_file_enables_button(self, picker, tmp_path):
        target = tmp_path / "a.txt"
        target.write_text("x")
        picker.open(mode="file", initial_dir=tmp_path)
        picker._on_item_click(target, is_dir=False)
        assert picker._selected_file == target
        assert picker._select_btn.disabled is False

    def test_navigating_into_dir_resets_selection(self, picker, tmp_path):
        target = tmp_path / "a.txt"
        target.write_text("x")
        subdir = tmp_path / "sub"
        subdir.mkdir()
        picker.open(mode="file", initial_dir=tmp_path)
        picker._on_item_click(target, is_dir=False)
        assert picker._select_btn.disabled is False
        picker._on_item_click(subdir, is_dir=True)
        assert picker._selected_file is None
        assert picker._select_btn.disabled is True


class TestSelectAction:
    def test_file_mode_returns_selected_file(self, picker, tmp_path):
        target = tmp_path / "a.txt"
        target.write_text("x")
        picker.open(mode="file", initial_dir=tmp_path)
        picker._on_item_click(target, is_dir=False)
        picker._on_select(None)
        assert picker._results == [str(target)]

    def test_file_mode_without_selection_returns_none(self, picker, tmp_path):
        picker.open(mode="file", initial_dir=tmp_path)
        picker._on_select(None)
        assert picker._results == [None]

    def test_folder_mode_returns_current_path(self, picker, tmp_path):
        picker.open(mode="folder", initial_dir=tmp_path)
        picker._on_select(None)
        assert picker._results == [str(tmp_path)]

    def test_cancel_returns_none(self, picker, tmp_path):
        picker.open(mode="file", initial_dir=tmp_path)
        picker._on_cancel()
        assert picker._results == [None]


class TestApplyEntries:
    def test_stale_token_ignored(self, picker):
        picker._current_path = Path("/somewhere")
        picker._mode = "file"
        picker._apply_entries(("elsewhere", "file"), [(False, Path("/tmp/x.txt"))])
        assert picker._file_list.controls == []

    def test_file_mode_filters_non_txt(self, picker, tmp_path):
        picker._current_path = tmp_path
        picker._mode = "file"
        txt = tmp_path / "keep.txt"
        py = tmp_path / "skip.py"
        picker._apply_entries((str(tmp_path), "file"), [(False, txt), (False, py)])
        names = [c.content.controls[1].value for c in picker._file_list.controls]
        assert names == ["keep.txt"]

    def test_dir_shown_with_suffix(self, picker, tmp_path):
        sub = tmp_path / "sub"
        picker._current_path = tmp_path
        picker._mode = "folder"
        picker._apply_entries((str(tmp_path), "folder"), [(True, sub)])
        names = [c.content.controls[1].value for c in picker._file_list.controls]
        assert names == ["sub/"]
