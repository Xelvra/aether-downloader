import datetime
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import flet as ft

import stahovac.gui.theme as th
from stahovac.core.metadata import MetadataError, MetadataService
from stahovac.core.validator import is_valid_url
from stahovac.gui.theme import (
    BREAKPOINT_COMPACT,
    BREAKPOINT_MOBILE_NAV,
    COLOR_ACCENT,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_SECONDARY,
    action_button,
    sz,
)
from stahovac.models import VideoMetadata

logger = logging.getLogger(__name__)


class DownloadView:
    def __init__(
        self,
        page,
        metadata_service: MetadataService,
        config,
        on_start_download: Callable,
        on_cancel_download: Callable,
        on_metadata_fetched: Callable | None = None,
    ):
        self._page = page
        self._metadata = metadata_service
        self._config = config
        self._on_start = on_start_download
        self._on_cancel = on_cancel_download
        self._on_metadata_fetched = on_metadata_fetched
        self._last_url_fetched = ""
        self._debounce_timer: threading.Timer | None = None
        self._metadata_request_id = 0
        self._closed = False
        self._metadata_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meta")

        self.refresh_overlay = ft.Container(
            content=ft.Icon(ft.Icons.REFRESH_ROUNDED, size=sz(16), color=COLOR_ACCENT),
            tooltip="Znovu načíst metadata",
            right=sz(4),
            top=0,
            bottom=0,
            width=sz(24),
            alignment=ft.Alignment(0, 0),
            on_click=self._on_refresh_click,
        )

        self.url_input = ft.TextField(
            label="Odkaz na video",
            hint_text="Vložte URL adresu",
            border_color=COLOR_ACCENT,
            focused_border_color=COLOR_ACCENT,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            border_radius=sz(8),
            expand=True,
        )
        self.url_input.on_change = self._on_url_change

        self.url_row = ft.Stack(
            [self.url_input, self.refresh_overlay],
            expand=True,
        )

        self.thumbnail_img = ft.Image(
            src="",
            visible=False,
            border_radius=sz(8),
            width=sz(160),
            height=sz(90),
            fit=ft.BoxFit.COVER,
        )
        self.meta_title = ft.Text(
            "",
            size=sz(15),
            weight=ft.FontWeight.BOLD,
            color=COLOR_TEXT,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=2,
        )
        self.meta_author = ft.Text("", size=sz(13), color=COLOR_ACCENT)
        self.meta_duration = ft.Text("", size=sz(13), color=COLOR_TEXT_SECONDARY)

        self.metadata_card = ft.Card(
            content=ft.Container(
                content=ft.Row(
                    [
                        self.thumbnail_img,
                        ft.Column(
                            [self.meta_title, self.meta_author, self.meta_duration],
                            spacing=sz(4),
                            expand=True,
                        ),
                    ],
                    spacing=sz(12),
                ),
                padding=sz(12),
                bgcolor=COLOR_SURFACE,
            ),
            elevation=3,
            visible=False,
        )

        self.download_button = action_button(
            ft.Icons.DOWNLOAD_ROUNDED,
            "Stáhnout",
            "#1976D2",
            self._on_download_click,
        )

        self.cancel_button = action_button(
            ft.Icons.CANCEL,
            "Zrušit",
            "#C62828",
            lambda e: self._on_cancel(),
        )
        self.cancel_button.disabled = True

    def _build_metadata_card(self, compact: bool) -> None:
        content: ft.Control
        if compact:
            self.thumbnail_img.width = sz(180)
            self.thumbnail_img.height = sz(101)
            content = ft.Column(
                [
                    self.thumbnail_img,
                    ft.Column([self.meta_title, self.meta_author, self.meta_duration], spacing=sz(4)),
                ],
                spacing=sz(8),
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            self.thumbnail_img.width = sz(160)
            self.thumbnail_img.height = sz(90)
            content = ft.Row(
                [
                    self.thumbnail_img,
                    ft.Column([self.meta_title, self.meta_author, self.meta_duration], spacing=sz(4), expand=True),
                ],
                spacing=sz(12),
            )
        self.metadata_card.content = ft.Container(content=content, padding=sz(12), bgcolor=COLOR_SURFACE)

    def build(self):
        compact = th.SCREEN_WIDTH < BREAKPOINT_COMPACT
        mobile = th.SCREEN_WIDTH < BREAKPOINT_MOBILE_NAV
        self._build_metadata_card(compact)
        button_row = (
            ft.Column(
                [self.download_button, self.cancel_button],
                spacing=sz(8),
            )
            if mobile
            else ft.Row(
                [self.download_button, self.cancel_button],
                spacing=sz(12),
            )
        )
        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Vložte odkaz pro rychlé stažení:",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                            ),
                            self.url_row,
                            self.metadata_card,
                            button_row,
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

    def _get_url(self):
        value = self.url_input.value
        return "" if value is None else str(value).strip()

    def _on_url_change(self, e):
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(0.4, self.refresh_metadata)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _on_refresh_click(self, e):
        self.refresh_metadata()

    def _on_download_click(self, e):
        self._on_start(self._get_url())

    def refresh_metadata(self):
        url = self._get_url()
        if not is_valid_url(url):
            return
        self._last_url_fetched = url
        self._metadata_request_id += 1
        request_id = self._metadata_request_id

        def fetch_worker():
            try:
                metadata = self._metadata.fetch(url, self._config)
            except MetadataError as e:
                logger.warning("Metadata fetch selhal pro %s: %s", url, e)
                metadata = None
            if request_id != self._metadata_request_id:
                return
            if self._last_url_fetched != url:
                return
            if self._on_metadata_fetched:
                self._on_metadata_fetched(metadata)

        if self._closed:
            return
        try:
            self._metadata_executor.submit(fetch_worker)
        except RuntimeError:
            self._metadata_request_id += 1

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._debounce_timer:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        self._metadata_request_id += 1
        self._metadata_executor.shutdown(wait=False, cancel_futures=True)

    def update_metadata_ui(self, metadata: VideoMetadata | None) -> None:
        if metadata is None:
            self.meta_title.value = self._get_url()
            self.meta_author.value = "Neznámý kanál"
            self.meta_duration.value = "Neznámá délka"
            self.thumbnail_img.visible = False
            self.metadata_card.visible = True
            return
        self.meta_title.value = metadata.title
        self.meta_author.value = f"Kanál: {metadata.uploader}"
        self.meta_duration.value = f"Délka: {str(datetime.timedelta(seconds=int(metadata.duration or 0)))}"
        if metadata.thumbnail:
            self.thumbnail_img.src = metadata.thumbnail
            self.thumbnail_img.visible = True
        else:
            self.thumbnail_img.visible = False
        self.metadata_card.visible = True

    def set_downloading(self, active: bool) -> None:
        self.download_button.disabled = active
        self.cancel_button.disabled = not active
        self.url_input.disabled = active
