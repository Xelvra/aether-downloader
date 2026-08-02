import time
from pathlib import Path

import flet as ft

import stahovac.gui.theme as th
from stahovac.config.constants import COOKIES_FILE_OPTION, COOKIES_NONE, COOKIES_SOURCES
from stahovac.core.ffmpeg import get_ffmpeg_version
from stahovac.gui.custom_file_picker import CustomFilePicker
from stahovac.gui.theme import (
    BREAKPOINT_COMPACT,
    BREAKPOINT_MOBILE_NAV,
    COLOR_ACCENT,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_SECONDARY,
    COLOR_WARN,
    sz,
)
from stahovac.utils.paths import get_base_dir
from stahovac.utils.system import open_path


class StorageView:
    def __init__(self, page, state, on_save_callback, on_ffmpeg_install=None):
        self._page = page
        self._state = state
        self._on_save = on_save_callback
        self._on_ffmpeg_install = on_ffmpeg_install
        self._last_dialog_time = 0.0
        self._initialized = False

        self._file_picker = CustomFilePicker(page, on_result=self._on_picker_result)

        self.output_folder_text = ft.Text(
            state.config.get("output_folder", str(get_base_dir())),
            size=sz(13),
            color=COLOR_ACCENT,
            italic=False,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
            max_lines=2,
        )

        self.cookies_dropdown = ft.Dropdown(
            label="Importovat cookies z prohlížeče",
            options=[ft.DropdownOption(text=c) for c in COOKIES_SOURCES],
            value=state.config.get("cookies_source", COOKIES_NONE),
            border_color=COLOR_TEXT_SECONDARY,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            expand=1,
            border_radius=sz(8),
            on_select=lambda e: self._handle_cookies_source_change(e),
        )

        self.cookies_file_text = ft.Text(
            state.config.get("cookies_file_path", ""),
            size=sz(12),
            color=COLOR_ACCENT,
            italic=False,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
            max_lines=2,
        )

        self.cookies_file_row = ft.Row(
            [
                ft.Text("Soubor cookies:", size=sz(12), color=COLOR_TEXT_SECONDARY),
                self.cookies_file_text,
                ft.IconButton(
                    icon=ft.Icons.FILE_OPEN_ROUNDED,
                    icon_color=COLOR_PRIMARY,
                    icon_size=sz(20),
                    on_click=self._select_cookies_file,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            visible=(state.config.get("cookies_source") == COOKIES_FILE_OPTION),
        )

        self._initialized = True

    def _build_output_row(self, mobile: bool) -> ft.Control:
        open_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN_ROUNDED,
            icon_color=COLOR_PRIMARY,
            icon_size=sz(20),
            tooltip="Vybrat složku",
            on_click=self._pick_folder,
        )
        launch_btn = ft.IconButton(
            icon=ft.Icons.LAUNCH_ROUNDED,
            icon_color=COLOR_SUCCESS,
            icon_size=sz(20),
            tooltip="Otevřít v průzkumníku",
            on_click=self._open_output_folder,
        )
        if mobile:
            return ft.Column(
                [self.output_folder_text, ft.Row([open_btn, launch_btn], spacing=sz(8))],
                spacing=sz(4),
            )
        return ft.Row(
            [self.output_folder_text, open_btn, launch_btn], spacing=sz(12), alignment=ft.MainAxisAlignment.CENTER
        )

    def _open_output_folder(self, e=None):
        ok, message = open_path(self.output_folder_text.value)
        if not ok:
            self._notify(message)

    def _notify(self, message: str) -> None:
        snackbar = ft.SnackBar(content=ft.Text(message), open=True)
        self._page.overlay.append(snackbar)
        snackbar.on_dismiss = lambda e: self._page.overlay.remove(snackbar) if snackbar in self._page.overlay else None
        self._page.update()

    def build(self):
        compact = th.SCREEN_WIDTH < BREAKPOINT_COMPACT
        mobile = th.SCREEN_WIDTH < BREAKPOINT_MOBILE_NAV

        output_row = self._build_output_row(mobile)
        ffmpeg_row = self._build_ffmpeg_row()

        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Místo pro uložení:",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                                visible=not compact,
                            ),
                            output_row,
                            ft.Divider(height=1, color=COLOR_SURFACE),
                            ft.Text(
                                "Nastavení cookies (obcházení limitů / Kick / Twitch):",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                            ),
                            ft.Column(
                                [self.cookies_dropdown],
                                spacing=sz(8),
                            ),
                            self.cookies_file_row,
                            ft.Divider(height=1, color=COLOR_SURFACE),
                            ft.Text(
                                "FFmpeg:",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                            ),
                            ffmpeg_row,
                        ],
                        spacing=sz(16),
                    ),
                    padding=sz(4),
                ),
            ],
            spacing=sz(16),
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
        )

    def _build_ffmpeg_row(self):
        version = get_ffmpeg_version()
        installed = version is not None
        label = "Přeinstalovat FFmpeg" if installed else "Stáhnout FFmpeg"
        status = f"FFmpeg: nainstalováno ✓ (v{version})" if installed else "FFmpeg: nenainstalováno"
        color = COLOR_SUCCESS if installed else COLOR_WARN
        button = ft.Button(
            label,
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda e: self._on_ffmpeg_install() if self._on_ffmpeg_install else None,
        )
        return ft.Row(
            [
                ft.Text(status, size=sz(13), color=color, expand=True),
                button,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=sz(12),
        )

    def _on_picker_result(self, path: str | None):
        if not path:
            return
        if self._picker_mode == "folder":
            norm_path = str(Path(path).resolve())
            self._state.config["output_folder"] = norm_path
            self.output_folder_text.value = norm_path
        elif self._picker_mode == "file":
            norm_path = str(Path(path).resolve())
            self._state.config["cookies_file_path"] = norm_path
            self.cookies_file_text.value = norm_path
        self._on_save()
        self._page.update()

    def _pick_folder(self, e):
        now = time.time()
        if now - self._last_dialog_time < 2.0:
            return
        self._last_dialog_time = now
        self._picker_mode = "folder"
        self._file_picker.open(mode="folder", initial_dir=self.output_folder_text.value)

    def _select_cookies_file(self, e):
        now = time.time()
        if now - self._last_dialog_time < 2.0:
            return
        self._last_dialog_time = now
        self._picker_mode = "file"
        self._file_picker.open(mode="file", initial_dir=self.cookies_file_text.value or str(Path.home()))

    def _handle_cookies_source_change(self, e):
        self.cookies_file_row.visible = self.cookies_dropdown.value == COOKIES_FILE_OPTION
        self._on_save()
        self._page.update()
