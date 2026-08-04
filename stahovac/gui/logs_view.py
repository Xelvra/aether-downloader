from pathlib import Path

import flet as ft

import stahovac.gui.theme as th
from stahovac.gui.theme import (
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_SECONDARY,
    ICON_SIZE,
    sz,
)
from stahovac.storage.history import HistoryManager
from stahovac.utils.system import open_path, reveal_in_file_manager


class LogsView:
    def __init__(self, page):
        self._page = page

        self.log_list_view = ft.ListView(
            spacing=0,
            auto_scroll=True,
            build_controls_on_demand=False,
            expand=True,
        )

        self.log_container = ft.Container(
            content=self.log_list_view,
            border=ft.Border(
                left=ft.BorderSide(1, COLOR_SURFACE),
                top=ft.BorderSide(1, COLOR_SURFACE),
                right=ft.BorderSide(1, COLOR_SURFACE),
                bottom=ft.BorderSide(1, COLOR_SURFACE),
            ),
            border_radius=sz(8),
            bgcolor=COLOR_SURFACE,
            padding=sz(8),
            height=max(sz(80), int(800 * 0.15)),
        )

        self.history_column = ft.Column(spacing=sz(4), expand=True, scroll=ft.ScrollMode.AUTO)

    def build(self):
        self.log_container.height = max(sz(80), int(th.SCREEN_WIDTH * 0.15))
        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Systémové logy:",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                            ),
                            self.log_container,
                            ft.Divider(height=1, color=COLOR_SURFACE),
                            ft.Text(
                                "Poslední stažené položky:",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                            ),
                            self.history_column,
                        ],
                        spacing=sz(16),
                    ),
                    padding=sz(4),
                ),
            ],
            spacing=sz(16),
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
        )

    def render_history(self):
        self.history_column.controls.clear()
        items = HistoryManager.load_history()
        if not items:
            self.history_column.controls.append(
                ft.Text(
                    "Žádná historie stahování.",
                    size=sz(12),
                    color=COLOR_TEXT_SECONDARY,
                    italic=True,
                )
            )
        else:
            for item in items:
                path_info = Path(item.get("file_path", ""))
                self.history_column.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.PLAY_CIRCLE_OUTLINED,
                                    size=ICON_SIZE,
                                    color=COLOR_ACCENT,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            item.get("title", "Soubor"),
                                            size=sz(13),
                                            weight=ft.FontWeight.BOLD,
                                            color=COLOR_TEXT,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                            max_lines=1,
                                            selectable=True,
                                        ),
                                        ft.Text(
                                            f"{path_info.name}  \u2022  {item.get('date', '')}",
                                            size=sz(11),
                                            color=COLOR_TEXT_SECONDARY,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                            selectable=True,
                                        ),
                                    ],
                                    expand=True,
                                    spacing=sz(2),
                                ),
                                self._history_action_buttons(item),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=sz(8),
                        border_radius=sz(8),
                        bgcolor=COLOR_SURFACE,
                    )
                )

    def _history_action_buttons(self, item: dict) -> ft.Row:
        file_path = item.get("file_path", "")
        return ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                    icon_color=COLOR_ACCENT,
                    icon_size=ICON_SIZE,
                    tooltip="Otevřít složku",
                    on_click=lambda e: self._reveal_history_item(file_path),
                ),
                ft.IconButton(
                    icon=ft.Icons.PLAY_CIRCLE_OUTLINED,
                    icon_color=COLOR_SUCCESS,
                    icon_size=ICON_SIZE,
                    tooltip="Otevřít video",
                    on_click=lambda e: self._open_history_item(file_path),
                ),
            ],
            spacing=sz(8),
        )

    def _open_history_item(self, file_path: str) -> None:
        ok, message = open_path(file_path)
        if not ok:
            th.notify(self._page, message)

    def _reveal_history_item(self, file_path: str) -> None:
        ok, message = reveal_in_file_manager(file_path)
        if not ok:
            th.notify(self._page, message)
