import threading
from pathlib import Path

import flet as ft

import stahovac.gui.theme as th
from stahovac.gui.theme import (
    BREAKPOINT_COMPACT,
    BREAKPOINT_MOBILE_NAV,
    COLOR_ACCENT,
    COLOR_SURFACE,
    COLOR_TEXT,
    sz,
)


class CustomFilePicker:
    def __init__(self, page, on_result):
        self._page = page
        self._on_result = on_result
        self._current_path = Path.home()
        self._mode = "folder"
        self._selected_file: Path | None = None
        self._build_ui()

    def _build_ui(self):
        self._path_text = ft.Text(
            str(self._current_path),
            size=sz(13),
            color=COLOR_ACCENT,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )

        self._file_list = ft.ListView(
            spacing=2,
            auto_scroll=False,
            expand=True,
        )

        self._select_btn = ft.Button(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK, size=sz(18), color="#FFFFFF"),
                    ft.Text("Vybrat", size=sz(14), weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                ],
                spacing=sz(6),
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(bgcolor=COLOR_ACCENT, shape=ft.RoundedRectangleBorder(radius=sz(8))),
            on_click=self._on_select,
        )

        cancel_btn = ft.Button(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CLOSE, size=sz(18), color="#FFFFFF"),
                    ft.Text("Zrušit", size=sz(14), weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                ],
                spacing=sz(6),
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(bgcolor="#555555", shape=ft.RoundedRectangleBorder(radius=sz(8))),
            on_click=self._on_cancel,
        )

        self._dialog_content = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.FOLDER_OPEN, size=sz(20), color=COLOR_ACCENT),
                                self._path_text,
                            ],
                            spacing=sz(8),
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(sz(4), sz(8), sz(4), sz(8)),
                    ),
                    ft.Divider(height=1),
                    ft.Container(
                        content=self._file_list,
                        expand=True,
                        padding=ft.Padding(0, sz(4), 0, sz(4)),
                    ),
                    ft.Divider(height=1),
                    ft.Container(
                        content=ft.Row(
                            [cancel_btn, self._select_btn],
                            alignment=ft.MainAxisAlignment.END,
                            spacing=sz(8),
                        ),
                        padding=ft.Padding(0, sz(8), 0, sz(4)),
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            padding=sz(16),
            bgcolor=COLOR_SURFACE,
            border_radius=sz(12),
            width=max(sz(360), 360),
            height=sz(400),
        )

        self._overlay = ft.Container(
            content=ft.Stack(
                [
                    ft.Container(expand=True, on_click=self._on_cancel),
                    ft.Container(content=self._dialog_content, alignment=ft.Alignment(0, 0)),
                ],
                expand=True,
            ),
            bgcolor=ft.Colors.with_opacity(0.6, "#000000"),
            visible=False,
            expand=True,
        )

        self._page.overlay.append(self._overlay)

    def open(self, mode="folder", initial_dir=None):
        self._mode = mode
        self._selected_file = None
        if initial_dir:
            self._current_path = Path(initial_dir).resolve()
        else:
            self._current_path = Path.home()
        mobile = th.SCREEN_WIDTH < BREAKPOINT_MOBILE_NAV
        if mobile:
            self._dialog_content.width = self._page.width - sz(16)
            self._dialog_content.height = min(self._page.height - sz(16), sz(500))
        else:
            compact = th.SCREEN_WIDTH < BREAKPOINT_COMPACT
            if compact:
                self._dialog_content.width = self._page.width - sz(16)
                self._dialog_content.height = self._page.height - sz(16)
            else:
                self._dialog_content.width = max(sz(360), 360)
                self._dialog_content.height = sz(400)
        self._refresh_list()
        self._overlay.visible = True
        self._page.update()

    def close(self):
        self._overlay.visible = False
        self._page.update()

    def _on_select(self, e):
        path = self._selected_file if self._mode == "file" else self._current_path
        result = str(path) if path else None
        self._overlay.visible = False
        self._page.update()
        self._on_result(result)

    def _on_cancel(self, e=None):
        self._overlay.visible = False
        self._page.update()
        self._on_result(None)

    def _refresh_list(self):
        self._file_list.controls.clear()
        self._path_text.value = str(self._current_path)
        self._select_btn.disabled = self._mode == "file" and self._selected_file is None

        if self._current_path.parent != self._current_path:
            self._file_list.controls.append(self._make_item("..", self._current_path.parent, True, False))

        self._page.update()
        threading.Thread(target=self._load_entries, daemon=True).start()

    def _load_entries(self):
        token = (str(self._current_path), self._mode)
        try:
            raw_entries = list(self._current_path.iterdir())
        except OSError:
            raw_entries = []

        items = []
        for entry in raw_entries:
            try:
                items.append((entry.is_dir(), entry))
            except OSError:
                continue
        items.sort(key=lambda pair: (not pair[0], pair[1].name.lower()))

        import contextlib

        with contextlib.suppress(Exception):
            self._page.run_thread(self._apply_entries, token, items)

    def _apply_entries(self, token: tuple, items: list):
        if token != (str(self._current_path), self._mode):
            return
        for is_dir, entry in items:
            if not is_dir and self._mode == "file" and entry.suffix.lower() != ".txt":
                continue
            selected = self._selected_file == entry
            self._file_list.controls.append(
                self._make_item(entry.name + "/" if is_dir else entry.name, entry, is_dir, selected)
            )
        self._page.update()

    def _make_item(self, display_name, path, is_dir, selected=False):
        icon_name = ft.Icons.FOLDER if is_dir else ft.Icons.DESCRIPTION
        bg = COLOR_ACCENT + "30" if selected else None

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon_name, size=sz(18), color=COLOR_ACCENT),
                    ft.Text(
                        display_name,
                        size=sz(13),
                        color=COLOR_TEXT,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=sz(8),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(sz(8), sz(4), sz(8), sz(4)),
            border_radius=sz(6),
            bgcolor=bg,
            on_click=lambda e, p=path, d=is_dir: self._on_item_click(p, d),
        )

    def _on_item_click(self, path: Path, is_dir: bool):
        if is_dir:
            self._current_path = path
            self._selected_file = None
            self._refresh_list()
        elif self._mode == "file":
            self._selected_file = path
            self._select_btn.disabled = False
            self._refresh_list()
