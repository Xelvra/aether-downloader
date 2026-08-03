import flet as ft

from stahovac.gui.theme import (
    COLOR_ACCENT,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_SECONDARY,
    ICON_SIZE_LARGE,
    sz,
)
from stahovac.help_content import HELP_SECTIONS, HelpCode, HelpQA, HelpText


def _section(title: str, *items: str) -> ft.Column:
    return ft.Column(
        [
            ft.Text(title, size=sz(16), weight=ft.FontWeight.BOLD, color=COLOR_ACCENT),
            ft.Column(
                [ft.Text(item, size=sz(13), color=COLOR_TEXT, selectable=True) for item in items],
                spacing=sz(6),
            ),
        ],
        spacing=sz(8),
    )


_COMMENT_COLOR = "#707090"
_CMD_COLOR = COLOR_ACCENT


def _code_block(*lines: str) -> ft.Container:
    children: list[ft.Control] = []
    for line in lines:
        color = _COMMENT_COLOR if line.startswith("#") else _CMD_COLOR
        children.append(ft.Text(line, size=sz(12), color=color, font_family="monospace", selectable=True))
    return ft.Container(
        content=ft.Column(children, spacing=sz(2)),
        padding=sz(12),
        border_radius=sz(8),
        bgcolor="#1A1A2E",
    )


def _qa(question: str, answer: str) -> ft.Column:
    return ft.Column(
        [
            ft.Text(question, size=sz(13), weight=ft.FontWeight.BOLD, color=COLOR_TEXT),
            ft.Text(answer, size=sz(13), color=COLOR_TEXT, selectable=True),
        ],
        spacing=sz(2),
    )


def _content_children() -> list[ft.Control]:
    children: list[ft.Control] = []
    for section in HELP_SECTIONS:
        if isinstance(section, HelpText):
            children.append(_section(section.title, *section.items))
        elif isinstance(section, HelpCode):
            children.append(_code_block(*section.lines))
        elif isinstance(section, HelpQA):
            if section.title:
                children.append(_section(section.title))
            children.extend(_qa(question, answer) for question, answer in section.items)
        else:
            raise AssertionError(f"neznámý typ sekce nápovědy: {section!r}")
    return children


def build_help_content(dismiss_callback) -> ft.Container:
    scrollable = ft.Container(
        content=ft.Column(
            [
                ft.Text("Nápověda", size=sz(20), weight=ft.FontWeight.BOLD, color=COLOR_TEXT),
                ft.Divider(color=COLOR_SURFACE),
                *_content_children(),
                ft.Divider(color=COLOR_SURFACE),
                ft.Text(
                    "Další informace najdeš v README nebo na GitHub Issues.",
                    size=sz(12),
                    color=COLOR_TEXT_SECONDARY,
                    italic=True,
                ),
            ],
            spacing=sz(16),
            scroll=ft.ScrollMode.ALWAYS,
        ),
        padding=ft.Padding(sz(48), sz(20), sz(20), sz(20)),
        expand=True,
    )

    close_btn = ft.Container(
        content=ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_color=COLOR_TEXT_SECONDARY,
            icon_size=ICON_SIZE_LARGE,
            on_click=lambda e: dismiss_callback(),
        ),
        right=sz(8),
        top=sz(8),
    )

    return ft.Container(
        content=ft.Stack([scrollable, close_btn]),
        bgcolor=COLOR_SURFACE,
        border_radius=sz(12),
        expand=True,
    )
