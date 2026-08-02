import threading
import time
import traceback

import flet as ft

import stahovac.gui.theme as th
from stahovac.config.constants import APP_TITLE, COOKIES_FILE_OPTION, FORMAT_MP4, VERSION_DISPLAY
from stahovac.core import ffmpeg
from stahovac.core.validator import validate_crf, validate_time_range
from stahovac.downloader import DownloadManager
from stahovac.gui.download_view import DownloadView
from stahovac.gui.help_view import build_help_content
from stahovac.gui.logs_view import LogsView
from stahovac.gui.quality_view import QualityView
from stahovac.gui.storage_view import StorageView
from stahovac.gui.theme import (
    BREAKPOINT_COMPACT,
    BREAKPOINT_MOBILE_NAV,
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_TEXT_SECONDARY,
    COLOR_WARN,
    sz,
)
from stahovac.models import DownloadParams
from stahovac.utils.cookies import validate_cookies_file


class GuiApp:
    _CANCEL_FORCE_STOP_DELAY = 8.0
    _CANCEL_FORCE_UNLOCK_DELAY = 8.0

    def __init__(self, page: ft.Page, manager: DownloadManager | None = None):
        self._page = page
        th.set_screen_width(self._read_page_width())

        self._manager = manager or DownloadManager(
            on_log=self._on_log_received,
            on_progress=self._on_progress_changed,
            on_status=self._on_status_changed,
            on_finish=self._on_download_finished,
        )
        self._active_tab = 0
        self._config = self._manager.state.config
        self._is_downloading = False

        self._pending_logs: list[ft.Text] = []
        self._last_log_update = 0.0
        self._last_progress_update = 0.0
        self._pending_download: DownloadParams | None = None
        self._unlock_timer: threading.Timer | None = None
        self._ui_lock = threading.Lock()
        self._resize_timer: threading.Timer | None = None

        self._setup_page()
        self._build_help_overlay()
        self._build_nav_drawer()
        self._build_views()
        self._build_header()
        self._build_progress()
        self._build_nav()
        self._build_content_area()
        self._build_layout()
        self._ensure_system_deps()
        self._page.update()

    def _run_ui_thread(self, handler, *args) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            self._page.run_thread(handler, *args)

    def _read_page_width(self) -> int:
        try:
            width = int(getattr(self._page, "width", 0) or 0)
        except (TypeError, ValueError):
            width = 0
        return width if width > 0 else 800

    def _setup_page(self):
        self._page.title = f"{APP_TITLE} – {VERSION_DISPLAY}"
        try:
            self._page.window.min_width = 400
            self._page.window.min_height = 500
            self._page.window.width = 720
            self._page.window.height = 820
        except AttributeError:
            self._page.window_width = 720  # type: ignore[attr-defined]  # legacy flet fallback
            self._page.window_height = 820  # type: ignore[attr-defined]
            self._page.window_min_width = 400  # type: ignore[attr-defined]
            self._page.window_min_height = 500  # type: ignore[attr-defined]
        self._page.theme_mode = ft.ThemeMode.DARK
        self._page.padding = 20
        self._page.bgcolor = COLOR_BG
        self._page.on_resize = self._on_page_resized
        self._page.on_close = self._on_page_close

    def _on_page_resized(self, e):
        try:
            import json

            data = json.loads(e.data) if isinstance(getattr(e, "data", None), str) else {}
            width = int(data.get("width", getattr(e, "width", 0)))
        except (ValueError, TypeError):
            width = 0
        if width <= 0:
            width = self._read_page_width()
        th.set_screen_width(width)
        if self._resize_timer:
            self._resize_timer.cancel()
        self._resize_timer = threading.Timer(0.15, self._schedule_apply_resize)
        self._resize_timer.daemon = True
        self._resize_timer.start()

    def _schedule_apply_resize(self):
        self._resize_timer = None
        self._run_ui_thread(self._apply_resize)

    def _apply_resize(self):
        self._rebuild_active_tab()
        self._rebuild_header()
        self._rebuild_nav()
        self._safe_page_update()

    def _rebuild_active_tab(self):
        idx = self._active_tab
        builders = [
            self.download_view.build,
            self.quality_view.build,
            self.storage_view.build,
            self.logs_view.build,
        ]
        self._tab_contents[idx] = builders[idx]()
        self._content_area.content = self._tab_contents[idx]

    def _is_mobile(self):
        return th.SCREEN_WIDTH < BREAKPOINT_MOBILE_NAV

    def _on_page_close(self):
        if self._unlock_timer:
            self._unlock_timer.cancel()
            self._unlock_timer = None
        if self._resize_timer:
            self._resize_timer.cancel()
            self._resize_timer = None
        self.download_view.close()
        if self._is_downloading:
            self._manager.cancel_download()
            self._manager.downloader.force_stop()

    # --- Help overlay ---

    def _build_help_overlay(self):
        self._help_overlay = ft.Container(
            content=build_help_content(dismiss_callback=self._close_help),
            bgcolor=COLOR_BG,
            visible=False,
            expand=True,
        )
        self._page.overlay.append(self._help_overlay)

    def _show_help(self, e=None):
        is_mobile = self._is_mobile()
        if is_mobile:
            self._help_overlay.width = self._page.width
            self._help_overlay.height = self._page.height
        else:
            self._help_overlay.width = None
            self._help_overlay.height = None
        self._help_overlay.visible = True
        self._page.update()

    def _close_help(self):
        self._help_overlay.visible = False
        self._page.update()

    # --- Navigation drawer (mobile) ---

    def _build_nav_drawer(self):
        icon_map = [
            ft.Icons.DOWNLOAD_ROUNDED,
            ft.Icons.CUT_ROUNDED,
            ft.Icons.SETTINGS_ROUNDED,
            ft.Icons.HISTORY,
        ]
        labels = ["Stahování", "Ořez", "Nastavení", "Historie"]

        destinations = []
        for i in range(4):
            destinations.append(
                ft.NavigationDrawerDestination(
                    icon=icon_map[i],
                    label=labels[i],
                )
            )
        destinations.append(
            ft.NavigationDrawerDestination(
                icon=ft.Icons.HELP_OUTLINE,
                label="Nápověda",
            )
        )

        self._nav_drawer = ft.NavigationDrawer(
            on_change=self._on_drawer_change,
        )
        for dest in destinations:
            self._nav_drawer.controls.append(dest)

        self._page.drawer = self._nav_drawer

    async def _on_drawer_change(self, e):
        idx = int(e.control.selected_index)
        if idx == 4:
            await self._page.close_drawer()
            self._show_help()
            return
        self._active_tab = idx
        self._rebuild_active_tab()
        await self._page.close_drawer()
        if idx == 3:
            self.logs_view.render_history()
        self._safe_page_update()

    async def _open_drawer(self, e=None):
        await self._page.show_drawer()

    # --- Views ---

    def _build_views(self):
        self.download_view = DownloadView(
            page=self._page,
            metadata_service=self._manager.downloader.metadata,
            config=self._config,
            on_start_download=self._on_start_download,
            on_cancel_download=self._on_cancel_download,
            on_metadata_fetched=self._on_metadata_fetched,
        )
        self.quality_view = QualityView(
            self._page,
            config=self._config,
            on_save_callback=self._on_save_settings,
        )
        self.storage_view = StorageView(
            page=self._page,
            state=self._manager.state,
            on_save_callback=self._on_save_settings,
            on_ffmpeg_install=self._on_download_ffmpeg,
        )
        self.logs_view = LogsView(self._page)

        self._tab_contents = [
            self.download_view.build(),
            self.quality_view.build(),
            self.storage_view.build(),
            self.logs_view.build(),
        ]

    # --- Header ---

    def _build_header(self):
        self._header_section = self._make_header()

    def _rebuild_header(self):
        new_header = self._make_header()
        self._header_section.content = new_header.content
        self._header_section.update()

    def _make_header(self):
        is_mobile = self._is_mobile()
        hamburger = (
            ft.IconButton(
                icon=ft.Icons.MENU,
                icon_color=COLOR_PRIMARY,
                icon_size=sz(24),
                tooltip="Menu",
                on_click=self._open_drawer,
            )
            if is_mobile
            else ft.Container(width=0, height=0, visible=False)
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(content=hamburger, expand=1, alignment=ft.Alignment(-1, 0)),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    APP_TITLE,
                                    size=sz(22),
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_PRIMARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(
                                    content=ft.Text(
                                        "Stahovač pro YouTube, Kick, Twitch a mnoho dalších",
                                        size=sz(11),
                                        color=COLOR_TEXT_SECONDARY,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    visible=th.SCREEN_WIDTH >= BREAKPOINT_COMPACT,
                                ),
                            ],
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                        ),
                        expand=3,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Container(
                        content=ft.IconButton(
                            icon=ft.Icons.HELP_OUTLINE,
                            icon_color=COLOR_TEXT_SECONDARY,
                            icon_size=sz(22),
                            tooltip="Nápověda",
                            on_click=self._show_help,
                        ),
                        expand=1,
                        alignment=ft.Alignment(1, 0),
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            margin=ft.Margin(0, 0, 0, sz(10)),
        )

    # --- Progress ---

    def _build_progress(self):
        self._progress_bar = ft.ProgressBar(visible=False, color=COLOR_ACCENT, bgcolor=COLOR_SURFACE, height=sz(6))
        self._status_text = ft.Text(
            "Připraven k práci",
            size=sz(12),
            weight=ft.FontWeight.BOLD,
            color=COLOR_SUCCESS,
            text_align=ft.TextAlign.CENTER,
        )
        self._ffmpeg_installing = False
        self._ffmpeg_cancel = threading.Event()
        self._last_ffmpeg_progress = 0.0
        self._ffmpeg_text = ft.Text("", size=sz(12), color=COLOR_WARN, text_align=ft.TextAlign.CENTER)
        self._ffmpeg_progress = ft.ProgressBar(visible=False, height=sz(4), color=COLOR_ACCENT, bgcolor=COLOR_SURFACE)
        self._ffmpeg_btn = ft.Button(
            "Stáhnout FFmpeg (cca 80 MB)",
            icon=ft.Icons.DOWNLOAD,
            on_click=self._on_download_ffmpeg,
        )
        self._ffmpeg_cancel_btn = ft.Button(
            "Zrušit",
            on_click=self._on_cancel_ffmpeg_download,
            visible=False,
        )
        self._ffmpeg_banner = ft.Container(
            content=ft.Column(
                [
                    self._ffmpeg_text,
                    self._ffmpeg_progress,
                    ft.Row(
                        [self._ffmpeg_btn, self._ffmpeg_cancel_btn],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=sz(8),
                    ),
                ],
                spacing=sz(4),
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            visible=False,
            bgcolor=COLOR_SURFACE,
            border_radius=sz(8),
            padding=sz(8),
            margin=ft.Margin(0, sz(4), 0, 0),
        )

    # --- Navigation ---

    def _build_nav(self):
        if self._is_mobile():
            self._tab_bar: ft.Container | ft.Row = ft.Container(height=0, visible=False)
        else:
            self._build_tab_bar()

    def _rebuild_nav(self):
        now_mobile = self._is_mobile()
        self._nav_was_mobile = now_mobile
        if now_mobile:
            self._tab_bar.visible = False
            self._tab_bar.height = 0
        else:
            self._tab_bar.visible = True
            self._tab_bar.height = None
            self._update_tab_bar()

    def _build_tab_bar(self):
        self._tab_buttons_row = ft.Row(spacing=4, alignment=ft.MainAxisAlignment.SPACE_AROUND)
        self._update_tab_bar()
        self._tab_bar = self._tab_buttons_row

    def _build_content_area(self):
        self._content_area = ft.Container(
            content=self._tab_contents[0],
            expand=True,
            margin=ft.Margin(0, sz(8), 0, 0),
        )

    def _make_tab_button(self, label: str, icon, index: int) -> ft.Container:
        is_active = self._active_tab == index
        compact = th.SCREEN_WIDTH < BREAKPOINT_COMPACT
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(icon, size=sz(16), color=COLOR_ACCENT if is_active else COLOR_TEXT_SECONDARY),
                    ft.Text(
                        label if not compact else "",
                        size=sz(10),
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_ACCENT if is_active else COLOR_TEXT_SECONDARY,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
                tight=True,
            ),
            padding=ft.Padding(sz(8), sz(6), sz(8), sz(6)),
            bgcolor=COLOR_SURFACE if is_active else None,
            border_radius=sz(8),
            ink=False,
            tooltip=label if compact else None,
            on_click=lambda e: self._switch_tab(index),
        )

    def _update_tab_bar(self):
        if not getattr(self, "_tab_buttons_row", None):
            self._tab_buttons_row = ft.Row(spacing=4, alignment=ft.MainAxisAlignment.SPACE_AROUND)
        self._tab_buttons_row.controls = [
            self._make_tab_button("Stahování", ft.Icons.DOWNLOAD_ROUNDED, 0),
            self._make_tab_button("Ořez", ft.Icons.CUT_ROUNDED, 1),
            self._make_tab_button("Nastavení", ft.Icons.SETTINGS_ROUNDED, 2),
            self._make_tab_button("Historie", ft.Icons.HISTORY, 3),
        ]

    def _apply_tab_states(self):
        for index, control in enumerate(self._tab_buttons_row.controls):
            if not isinstance(control, ft.Container):
                continue
            button = control
            is_active = self._active_tab == index
            button.bgcolor = COLOR_SURFACE if is_active else None
            column = button.content
            if not isinstance(column, ft.Column) or len(column.controls) < 2:
                continue
            icon, text = column.controls[0], column.controls[1]
            if not isinstance(icon, ft.Icon) or not isinstance(text, ft.Text):
                continue
            color = COLOR_ACCENT if is_active else COLOR_TEXT_SECONDARY
            icon.color = color
            text.color = color

    def _switch_tab(self, index: int):
        self._active_tab = index
        self._rebuild_active_tab()
        if index == 3:
            self.logs_view.render_history()
        if not self._is_mobile():
            self._apply_tab_states()
        self._safe_page_update()

    def _build_layout(self):
        self._page.add(
            ft.Container(
                content=ft.Column(
                    [
                        self._header_section,
                        self._tab_bar,
                        ft.Divider(height=1, color=COLOR_SURFACE),
                        self._content_area,
                        ft.Divider(height=1, color=COLOR_SURFACE),
                        ft.Container(
                            content=ft.Column(
                                [self._progress_bar, self._status_text, self._ffmpeg_banner],
                                spacing=sz(4),
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            margin=ft.Margin(0, sz(4), 0, 0),
                        ),
                    ],
                    spacing=0,
                    expand=True,
                ),
                padding=sz(8),
                expand=True,
            )
        )

    def _ensure_system_deps(self):
        if ffmpeg.find_ffmpeg() is None:
            self._ffmpeg_text.value = "⚠️ FFmpeg není nainstalován – bez něj nepůjde ořez videa ani převod na MP3."
            self._ffmpeg_banner.visible = True
            self._safe_page_update()

    def _on_download_ffmpeg(self, e=None):
        if self._ffmpeg_installing:
            return
        self._ffmpeg_installing = True
        self._ffmpeg_cancel = threading.Event()
        self._ffmpeg_text.value = "Stahuji a instaluji FFmpeg…"
        self._ffmpeg_btn.visible = False
        self._ffmpeg_cancel_btn.visible = True
        self._ffmpeg_progress.visible = True
        self._ffmpeg_progress.value = None
        self._ffmpeg_banner.visible = True
        self._safe_page_update()
        threading.Thread(target=self._ffmpeg_install_worker, daemon=True).start()

    def _ffmpeg_install_worker(self):
        def progress(percent, speed, eta):
            self._run_ui_thread(self._apply_ffmpeg_progress, percent, speed, eta)

        try:
            installed = ffmpeg.download_and_install(
                progress_cb=progress,
                cancel_check=self._ffmpeg_cancel.is_set,
            )
        except Exception as ex:
            self._run_ui_thread(self._apply_ffmpeg_install_failed, str(ex))
        else:
            self._run_ui_thread(self._apply_ffmpeg_install_done, installed is not None)

    def _apply_ffmpeg_progress(self, percent, speed, eta):
        with self._ui_lock:
            now = time.time()
            if now - self._last_ffmpeg_progress < 0.15:
                return
            self._last_ffmpeg_progress = now
            self._ffmpeg_progress.value = percent / 100.0
            self._ffmpeg_text.value = f"FFmpeg: {percent:.1f}%  \u2022  {speed}  \u2022  Zbývá: {eta}"
            self._safe_page_update()

    def _apply_ffmpeg_install_done(self, ok: bool):
        with self._ui_lock:
            self._ffmpeg_installing = False
            self._ffmpeg_cancel_btn.visible = False
            self._ffmpeg_progress.visible = False
            if ok:
                self._ffmpeg_banner.visible = False
                self._status_text.value = "FFmpeg připraven – ořez a MP3 jsou k dispozici."
                self._status_text.color = COLOR_SUCCESS
                self._rebuild_active_tab()
            else:
                self._ffmpeg_btn.visible = True
                self._ffmpeg_text.value = "Stažení FFmpeg se nepodařilo. Zkus to znovu."
            self._safe_page_update()

    def _apply_ffmpeg_install_failed(self, error: str):
        with self._ui_lock:
            self._ffmpeg_installing = False
            self._ffmpeg_btn.visible = True
            self._ffmpeg_cancel_btn.visible = False
            self._ffmpeg_progress.visible = False
            self._ffmpeg_text.value = (
                f"Stažení FFmpeg selhalo ({error}). Návod na ruční instalaci najdeš "
                "v nápovědě (ikona ❓ v horní liště)."
            )
            self._safe_page_update()

    def _on_cancel_ffmpeg_download(self, e=None):
        self._ffmpeg_cancel.set()

    def _safe_page_update(self):
        import contextlib

        with contextlib.suppress(Exception):
            self._page.update()

    def _schedule_force_stop(self):
        if self._unlock_timer:
            self._unlock_timer.cancel()
        self._unlock_timer = threading.Timer(self._CANCEL_FORCE_STOP_DELAY, self._force_stop_stage)
        self._unlock_timer.daemon = True
        self._unlock_timer.start()

    def _force_stop_stage(self):
        """1. fáze po zrušení: worker dostal čas na čisté ukončení (DownloadCancelled).
        Pokud neodpověděl, násilně ukončí child procesy (např. FFmpeg)."""
        if not self._is_downloading:
            return
        self._manager.downloader.force_stop()
        self.on_status("Stahování se nedaří ukončit – vynucuji zastavení.", COLOR_WARN)
        self._unlock_timer = threading.Timer(self._CANCEL_FORCE_UNLOCK_DELAY, self._force_unlock_stage)
        self._unlock_timer.daemon = True
        self._unlock_timer.start()

    def _force_unlock_stage(self):
        """2. fáze: poslední záchrana – odemkne UI, i když worker neodpovídá."""
        self._unlock_timer = None
        if not self._is_downloading:
            return
        self.on_status("Stahování bylo násilně ukončeno (worker neodpověděl).", COLOR_WARN)
        self._run_ui_thread(self._force_unlock_ui)

    # --- Direct UI updates (marshaled onto UI thread) ---

    def _append_logs(self):
        if self._pending_logs:
            self.logs_view.log_list_view.controls.extend(self._pending_logs)
            self._pending_logs.clear()
            if len(self.logs_view.log_list_view.controls) > 500:
                del self.logs_view.log_list_view.controls[:100]

    def _apply_log(self, text: str):
        cleaned = text.replace("\u2705 ", "").replace("\u274c ", "").replace("\u26a0\ufe0f ", "")
        with self._ui_lock:
            self._pending_logs.append(
                ft.Text(
                    cleaned,
                    size=sz(11),
                    font_family="monospace",
                    color=COLOR_TEXT_SECONDARY,
                    selectable=True,
                    enable_interactive_selection=True,
                )
            )
            now = time.time()
            if now - self._last_log_update > 0.2:
                self._append_logs()
                self._last_log_update = now
                self._safe_page_update()

    def _apply_progress(self, percent: float, speed: str, eta: str):
        with self._ui_lock:
            now = time.time()
            if now - self._last_progress_update > 0.15:
                self._last_progress_update = now
                self._progress_bar.value = percent / 100.0
                self._status_text.value = f"Stahování: {percent:.1f}%  \u2022  {speed}  \u2022  Zbývá: {eta}"
                self._safe_page_update()

    def _apply_status(self, text: str, color: str):
        with self._ui_lock:
            self._append_logs()
            self._status_text.value = text
            self._status_text.color = color
            self._safe_page_update()

    def _apply_finish(self, success: bool, msg: str):
        with self._ui_lock:
            self._force_unlock_ui()
            self._pending_download = None
            if success:
                self.logs_view.render_history()
            self._safe_page_update()

    def _apply_meta(self, metadata):
        with self._ui_lock:
            self.download_view.update_metadata_ui(metadata)
            if metadata and metadata.available_resolutions:
                self.quality_view.update_qualities(metadata.available_resolutions)
            self._safe_page_update()

    # --- Callbacks from background threads ---

    def _on_log_received(self, text: str):
        self._run_ui_thread(self._apply_log, text)

    def _on_progress_changed(self, job_id: str, percent: float, speed: str, eta: str):
        self._run_ui_thread(self._apply_progress, percent, speed, eta)

    def on_status(self, text: str, color: str):
        self._run_ui_thread(self._apply_status, text, color)

    def _on_status_changed(self, job_id: str, text: str, color: str):
        self.on_status(text, color)

    def _on_metadata_fetched(self, metadata):
        self._run_ui_thread(self._apply_meta, metadata)

    def _on_download_finished(self, job_id: str, success: bool, msg: str):
        self._run_ui_thread(self._apply_finish, success, msg)

    # --- Download lifecycle ---

    def _on_start_download(self, url: str):
        try:
            self._start_download_impl(url)
        except Exception as ex:
            tb = traceback.format_exc()
            self._on_log_received(f"CHYBA v _on_start_download: {ex}\n{tb}")
            self.on_status(f"Vnitřní chyba: {ex}", COLOR_WARN)
            self._force_unlock_ui()
            self._safe_page_update()

    def _start_download_impl(self, url: str):
        if self._is_downloading:
            self.on_status("Stahování již probíhá – dokonči nebo zruš aktuální.", COLOR_WARN)
            return
        if not url:
            self.on_status("Neplatná URL: Zadej odkaz na video.", COLOR_WARN)
            self._force_unlock_ui()
            return
        quality_params = self.quality_view.to_params()
        if not quality_params["whole_video"]:
            error = validate_time_range(
                quality_params["start_time"],
                quality_params["end_time"],
                quality_params["end_option"],
            )
            if error:
                self.on_status(error, COLOR_WARN)
                self._force_unlock_ui()
                return
            crf_error = validate_crf(quality_params["crf"])
            if crf_error:
                self.on_status(crf_error, COLOR_WARN)
                self._force_unlock_ui()
                return
        params = DownloadParams(
            url=url,
            quality=quality_params["quality"],
            format_choice=quality_params["format_choice"],
            output_folder=self.storage_view.output_folder_text.value,
            whole_video=quality_params["whole_video"],
            start_time=quality_params["start_time"],
            end_time=quality_params["end_time"],
            end_option=quality_params["end_option"],
            re_encode=quality_params["re_encode"],
            crf=self._parse_crf(quality_params["crf"]),
            preset=quality_params["preset"],
        )
        self._do_start_download(params)

    @staticmethod
    def _parse_crf(value: str) -> int:
        try:
            crf = int(value)
        except (TypeError, ValueError):
            return 23
        return crf if 0 <= crf <= 51 else 23

    def _do_start_download(self, params: DownloadParams):
        self._pending_download = None
        self._is_downloading = True
        self.download_view.set_downloading(True)
        self._progress_bar.visible = True
        self._progress_bar.value = None
        self.logs_view.log_list_view.controls.clear()
        self._last_log_update = time.time()
        self._last_progress_update = time.time()
        self._safe_page_update()
        needs_ffmpeg = not params.whole_video or params.format_choice != FORMAT_MP4
        if needs_ffmpeg and ffmpeg.find_ffmpeg() is None:
            self.on_status(
                "FFmpeg chybí – bez něj ořez a MP3 nefungují. Stáhni ho tlačítkem v dolní liště.",
                COLOR_WARN,
            )
        started = self._manager.start_download(params)
        if not started:
            self._force_unlock_ui()
            self.on_status("Stahování ještě probíhá – počkej na dokončení nebo zruš.", COLOR_WARN)
            self._safe_page_update()

    def _force_unlock_ui(self):
        self._is_downloading = False
        self._progress_bar.visible = False
        self.download_view.set_downloading(False)
        if self._unlock_timer:
            self._unlock_timer.cancel()
            self._unlock_timer = None

    def _on_cancel_download(self):
        if not self._is_downloading:
            return
        self._manager.cancel_download()
        self.on_status("Ruším stahování…", COLOR_WARN)
        self._safe_page_update()
        self._schedule_force_stop()

    def _on_save_settings(self):
        quality = self.quality_view.quality_dropdown.value or ""
        fmt = self.quality_view.format_dropdown.value or ""
        output_folder = self.storage_view.output_folder_text.value
        cookies_source = self.storage_view.cookies_dropdown.value or ""
        cookies_file_path = self.storage_view.cookies_file_text.value
        re_encode = bool(self.quality_view.re_encode_checkbox.value)
        crf = self.quality_view.crf_input.value
        preset = self.quality_view.preset_dropdown.value or ""
        if cookies_source == COOKIES_FILE_OPTION:
            cookie_error = validate_cookies_file(cookies_file_path)
            if cookie_error:
                self.on_status(f"Cookies: {cookie_error}", COLOR_WARN)
                return
        self._manager.state.update_config_from_ui(
            quality, fmt, output_folder, cookies_source, cookies_file_path, re_encode, crf, preset
        )
        if self._manager.config_save(self._manager.state.config):
            self.on_status("Konfigurace byla bezpečně uložena!", COLOR_SUCCESS)
        else:
            self.on_status("Uložení se nezdařilo. Zkus to prosím znovu.", COLOR_WARN)
