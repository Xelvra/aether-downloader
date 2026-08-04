import flet as ft

from stahovac.gui.theme import notify, sz


class _FakePage:
    def __init__(self):
        self.overlay: list = []
        self.updates = 0

    def update(self):
        self.updates += 1


class TestNotify:
    def test_appends_snackbar_and_updates(self):
        page = _FakePage()
        notify(page, "zpráva")
        assert len(page.overlay) == 1
        assert isinstance(page.overlay[0], ft.SnackBar)
        assert page.updates == 1

    def test_dismiss_removes_snackbar(self):
        page = _FakePage()
        notify(page, "zpráva")
        snackbar = page.overlay[0]
        snackbar.on_dismiss(None)
        assert snackbar not in page.overlay


class TestSz:
    def test_scales_with_screen_width(self, monkeypatch):
        import stahovac.gui.theme as th

        monkeypatch.setattr(th, "SCREEN_WIDTH", 800)
        assert sz(10) == 14  # 10 * 1.4
        monkeypatch.setattr(th, "SCREEN_WIDTH", 300)
        assert sz(10) == 8  # 300/500=0.6 -> max(0.8,0.6)=0.8 -> 8
