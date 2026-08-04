import stahovac.gui.theme as th
from stahovac.gui.logs_view import LogsView


class _FakePage:
    def __init__(self):
        self.overlay = []
        self.updates = 0

    def update(self):
        self.updates += 1


def _make():
    return LogsView(_FakePage())


def _patch_history(monkeypatch, items):
    import stahovac.gui.logs_view as lv

    monkeypatch.setattr(lv.HistoryManager, "load_history", classmethod(lambda cls: items))


class TestRenderHistory:
    def test_empty_shows_placeholder(self, monkeypatch):
        _patch_history(monkeypatch, [])
        view = _make()
        view.render_history()
        assert len(view.history_column.controls) == 1
        assert view.history_column.controls[0].value == "Žádná historie stahování."

    def test_with_items_appends_entries_with_actions(self, monkeypatch):
        items = [{"title": "Video A", "file_path": "/tmp/a.mp4", "date": "2026-01-01 10:00:00"}]
        _patch_history(monkeypatch, items)
        view = _make()
        view.render_history()
        assert len(view.history_column.controls) == 1
        row = view.history_column.controls[0].content
        assert len(row.controls) == 3  # ikona + text + akce
        actions = row.controls[2]
        assert len(actions.controls) == 2  # otevřít složku + otevřít video


class TestOpenHistoryItem:
    def test_success_no_notify(self, monkeypatch):
        import stahovac.gui.logs_view as lv

        monkeypatch.setattr(lv, "open_path", lambda p: (True, ""))
        notified = []
        monkeypatch.setattr(th, "notify", lambda page, m: notified.append(m))
        view = _make()
        view._open_history_item("/tmp/a.mp4")
        assert notified == []

    def test_failure_notifies(self, monkeypatch):
        import stahovac.gui.logs_view as lv

        monkeypatch.setattr(lv, "open_path", lambda p: (False, "chyba"))
        notified = []
        monkeypatch.setattr(th, "notify", lambda page, m: notified.append(m))
        view = _make()
        view._open_history_item("/tmp/a.mp4")
        assert notified == ["chyba"]


class TestRevealHistoryItem:
    def test_success_no_notify(self, monkeypatch):
        import stahovac.gui.logs_view as lv

        monkeypatch.setattr(lv, "reveal_in_file_manager", lambda p: (True, ""))
        notified = []
        monkeypatch.setattr(th, "notify", lambda page, m: notified.append(m))
        view = _make()
        view._reveal_history_item("/tmp/a.mp4")
        assert notified == []

    def test_failure_notifies(self, monkeypatch):
        import stahovac.gui.logs_view as lv

        monkeypatch.setattr(lv, "reveal_in_file_manager", lambda p: (False, "chyba"))
        notified = []
        monkeypatch.setattr(th, "notify", lambda page, m: notified.append(m))
        view = _make()
        view._reveal_history_item("/tmp/a.mp4")
        assert notified == ["chyba"]


class TestBuild:
    def test_sets_log_container_height(self, monkeypatch):
        monkeypatch.setattr(th, "SCREEN_WIDTH", 800)
        view = _make()
        result = view.build()
        assert view.log_container.height == max(th.sz(80), int(800 * 0.15))
        assert result is not None
