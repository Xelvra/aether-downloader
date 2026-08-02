from pathlib import Path

from stahovac.config.constants import HISTORY_FILE_NAME
from stahovac.storage.history import HistoryManager
from stahovac.utils.paths import set_base_dir


class TestHistoryManager:
    def _history_path(self, tmp_path):
        return tmp_path / HISTORY_FILE_NAME

    def test_load_empty_when_no_file(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        assert HistoryManager.load_history() == []

    def test_append_and_load(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        file_path = tmp_path / "test.mp4"
        file_path.write_text("x")
        HistoryManager.append("Test Video", "https://example.com/video", str(file_path))
        history = HistoryManager.load_history()
        assert len(history) == 1
        assert history[0]["title"] == "Test Video"
        assert history[0]["url"] == "https://example.com/video"
        assert history[0]["file_path"] == str(file_path)
        assert "date" in history[0]

    def test_append_replaces_duplicate_url(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        first = tmp_path / "first.mp4"
        second = tmp_path / "second.mp4"
        first.write_text("x")
        second.write_text("x")
        HistoryManager.append("First", "https://example.com/video", str(first))
        HistoryManager.append("Second", "https://example.com/video", str(second))
        history = HistoryManager.load_history()
        assert len(history) == 1
        assert history[0]["title"] == "Second"

    def test_invalid_json_file(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        history_file = tmp_path / HISTORY_FILE_NAME
        history_file.write_text("not json", encoding="utf-8")
        assert HistoryManager.load_history() == []

    def test_non_list_json(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        history_file = tmp_path / HISTORY_FILE_NAME
        history_file.write_text('{"key": "value"}', encoding="utf-8")
        assert HistoryManager.load_history() == []

    def test_max_30_items(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        for i in range(35):
            file_path = tmp_path / f"{i}.mp4"
            file_path.write_text("x")
            HistoryManager.append(f"Video {i}", f"https://example.com/{i}", str(file_path))
        history = HistoryManager.load_history()
        assert len(history) <= 30

    def test_prunes_missing_files(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        existing = tmp_path / "exists.mp4"
        existing.write_text("x")
        missing = tmp_path / "gone.mp4"
        HistoryManager.append("Present", "https://example.com/1", str(existing))
        HistoryManager.append("Deleted", "https://example.com/2", str(missing))
        history = HistoryManager.load_history()
        assert len(history) == 1
        assert history[0]["title"] == "Present"

    def test_prune_persists_to_disk(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        existing = tmp_path / "exists.mp4"
        existing.write_text("x")
        missing = tmp_path / "gone.mp4"
        HistoryManager.append("Present", "https://example.com/1", str(existing))
        HistoryManager.append("Deleted", "https://example.com/2", str(missing))
        HistoryManager.load_history()
        import json

        on_disk = json.loads((tmp_path / HISTORY_FILE_NAME).read_text(encoding="utf-8"))
        assert [h["title"] for h in on_disk] == ["Present"]
        assert all(Path(h["file_path"]).is_file() for h in on_disk)

    def test_atomic_write_failure_is_silent(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)

        def fake_open(path, *args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("builtins.open", fake_open)
        HistoryManager.append("A", "https://example.com/a", "/tmp/a.mp4")  # should not raise
        assert HistoryManager.load_history() == []

    def test_atomic_write_leaves_no_temp_file(self, tmp_path, monkeypatch):
        set_base_dir(tmp_path)
        file_path = tmp_path / "a.mp4"
        file_path.write_text("x")
        HistoryManager.append("A", "https://example.com/a", str(file_path))
        assert not (tmp_path / "history.tmp").exists()
