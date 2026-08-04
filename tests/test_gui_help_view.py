import flet as ft
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


class TestBuildHelpContent:
    def test_returns_container_with_close_button(self):
        result = hv.build_help_content(dismiss_callback=lambda: None)
        assert isinstance(result, ft.Container)
        stack = result.content
        assert isinstance(stack, ft.Stack)
        assert len(stack.controls) == 2  # scrollovatelný obsah + zavírací tlačítko
