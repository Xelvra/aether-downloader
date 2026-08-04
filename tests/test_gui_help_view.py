import pytest

import stahovac.gui.help_view as hv
from stahovac.help_content import HelpCode, HelpQA, HelpText


class TestContentChildren:
    def test_renders_help_text(self, monkeypatch):
        monkeypatch.setattr(hv, "HELP_SECTIONS", [HelpText("Titulek", ("řádek1", "řádek2"))])
        children = hv._content_children()
        assert children

    def test_renders_help_code(self, monkeypatch):
        monkeypatch.setattr(hv, "HELP_SECTIONS", [HelpCode(("# komentář", "$ příkaz"))])
        assert hv._content_children()

    def test_renders_help_qa(self, monkeypatch):
        monkeypatch.setattr(hv, "HELP_SECTIONS", [HelpQA("Otázky", (("otázka", "odpověď"),))])
        assert hv._content_children()

    def test_unknown_section_raises(self, monkeypatch):
        monkeypatch.setattr(hv, "HELP_SECTIONS", [object()])
        with pytest.raises(AssertionError):
            hv._content_children()
