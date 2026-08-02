from typing import Any

import flet as ft

import stahovac.gui.theme as th
from stahovac.config.constants import FORMAT_MP4, FORMATS, QUALITY_BEST
from stahovac.gui.theme import (
    BREAKPOINT_COMPACT,
    BREAKPOINT_MOBILE_NAV,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_SECONDARY,
    sz,
)


class QualityView:
    def __init__(self, page, config=None, on_save_callback=None):
        self._page = page
        self._on_save = on_save_callback or (lambda: None)
        config = config or {}

        self.quality_dropdown = ft.Dropdown(
            label="Kvalita videa",
            options=[ft.DropdownOption(text=QUALITY_BEST)],
            value=config.get("quality", QUALITY_BEST),
            border_color=COLOR_TEXT_SECONDARY,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            expand=1,
            border_radius=sz(8),
            on_select=self._on_quality_changed,
        )

        self.format_dropdown = ft.Dropdown(
            label="Formát výstupu",
            options=[ft.DropdownOption(text=f) for f in FORMATS],
            value=config.get("format", FORMAT_MP4),
            border_color=COLOR_TEXT_SECONDARY,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            expand=1,
            border_radius=sz(8),
            on_select=self._on_format_changed,
        )

        self.whole_video_checkbox = ft.Checkbox(
            label="Stáhnout celé video bez ořezu",
            value=True,
            fill_color=COLOR_PRIMARY,
            on_change=self._toggle_time_inputs,
            label_style=ft.TextStyle(size=sz(13), color=COLOR_TEXT),
            tooltip=(
                "Rychlý ořez začne/skončí na nejbližším klíčovém snímku, takže nemusí být úplně přesný. "
                "Pro přesný ořez zaškrtni „Překódovat“."
            ),
        )

        self.start_time_input = ft.TextField(
            label="Začátek ořezu",
            value="00:00:00",
            hint_text="HH:MM:SS",
            border_color=COLOR_TEXT_SECONDARY,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            expand=1,
            border_radius=sz(8),
        )

        self.end_option_radio = ft.RadioGroup(
            content=ft.Row(
                [
                    ft.Radio(value="Do konce videa", label="Do konce"),
                    ft.Radio(value="Do určitého času", label="Do času"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=sz(16),
            ),
            value="Do konce videa",
            on_change=self._handle_end_option_change,
        )

        self.end_time_input = ft.TextField(
            label="Konec ořezu",
            value="00:10:00",
            hint_text="HH:MM:SS",
            border_color=COLOR_TEXT_SECONDARY,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            expand=1,
            border_radius=sz(8),
            disabled=True,
        )

        self.time_row: ft.Control = ft.Row(
            [self.start_time_input, self.end_option_radio, self.end_time_input],
            alignment=ft.MainAxisAlignment.CENTER,
            visible=False,
        )
        self._time_visible = False

        self.re_encode_checkbox = ft.Checkbox(
            label="Překódovat (přesnější ořez, pomalejší)",
            value=config.get("re_encode", False),
            fill_color=COLOR_PRIMARY,
            on_change=self._toggle_re_encode,
            label_style=ft.TextStyle(size=sz(13), color=COLOR_TEXT),
        )

        self.crf_input = ft.TextField(
            label="CRF (0–51, nižší = lepší)",
            value=str(config.get("crf", "23")),
            hint_text="23",
            border_color=COLOR_TEXT_SECONDARY,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            width=sz(100),
            border_radius=sz(8),
        )

        self.preset_dropdown = ft.Dropdown(
            label="Preset",
            options=[
                ft.DropdownOption(text="ultrafast"),
                ft.DropdownOption(text="superfast"),
                ft.DropdownOption(text="veryfast"),
                ft.DropdownOption(text="faster"),
                ft.DropdownOption(text="fast"),
                ft.DropdownOption(text="medium"),
                ft.DropdownOption(text="slow"),
            ],
            value=config.get("preset", "fast"),
            border_color=COLOR_TEXT_SECONDARY,
            text_size=sz(13),
            label_style=ft.TextStyle(size=sz(13)),
            expand=1,
            border_radius=sz(8),
        )

        self.re_encode_row: ft.Control = ft.Row(
            [self.crf_input, self.preset_dropdown],
            spacing=sz(12),
            visible=False,
        )
        self._reencode_visible = False

    def _build_time_row(self, compact: bool) -> ft.Control:
        controls: list[ft.Control] = [self.start_time_input, self.end_option_radio, self.end_time_input]
        if compact:
            return ft.Column(controls, spacing=sz(8), visible=self._time_visible)
        return ft.Row(controls, alignment=ft.MainAxisAlignment.CENTER, visible=self._time_visible)

    def _build_reencode_row(self, compact: bool) -> ft.Control:
        controls: list[ft.Control] = [self.crf_input, self.preset_dropdown]
        if compact:
            return ft.Column(controls, spacing=sz(8), visible=self._reencode_visible)
        return ft.Row(controls, spacing=sz(12), visible=self._reencode_visible)

    def build(self):
        compact = th.SCREEN_WIDTH < BREAKPOINT_COMPACT
        mobile = th.SCREEN_WIDTH < BREAKPOINT_MOBILE_NAV

        self.time_row = self._build_time_row(compact)
        self.re_encode_row = self._build_reencode_row(compact)
        self.crf_input.width = None if compact else sz(100)
        self.crf_input.expand = 1 if compact else 0

        fmt_row = (
            ft.Column(
                [self.quality_dropdown, self.format_dropdown],
                spacing=sz(8),
            )
            if mobile
            else ft.Row(
                [self.quality_dropdown, self.format_dropdown],
                spacing=sz(12),
            )
        )

        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Výchozí kvalita a typ média:",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                            ),
                            fmt_row,
                            ft.Divider(height=1, color=COLOR_SURFACE),
                            ft.Text(
                                "Ořez časové osy (vyžaduje FFmpeg):",
                                size=sz(15),
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT,
                            ),
                            self.whole_video_checkbox,
                            self.time_row,
                            self.re_encode_checkbox,
                            self.re_encode_row,
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

    def _on_quality_changed(self, e):
        self._on_save()

    def _on_format_changed(self, e):
        self._on_save()

    def _handle_end_option_change(self, e):
        self.end_time_input.disabled = self.end_option_radio.value == "Do konce videa"
        self._page.update()

    def _toggle_time_inputs(self, e):
        self._time_visible = not self.whole_video_checkbox.value
        self.time_row.visible = self._time_visible
        self._page.update()

    def _toggle_re_encode(self, e) -> None:
        self._reencode_visible = bool(self.re_encode_checkbox.value)
        self.re_encode_row.visible = self._reencode_visible
        self._on_save()
        self._page.update()

    def update_qualities(self, resolutions: list[int]) -> None:
        options = [ft.DropdownOption(text=QUALITY_BEST)]
        for h in resolutions:
            options.append(ft.DropdownOption(text=f"{h}p"))
        self.quality_dropdown.options = options
        current = self.quality_dropdown.value
        if current != QUALITY_BEST and current not in {f"{h}p" for h in resolutions}:
            self.quality_dropdown.value = QUALITY_BEST
            self._on_save()
        self._page.update()

    @staticmethod
    def _clean_text(value: Any) -> str:
        return "" if value is None else str(value).strip()

    def to_params(self) -> dict[str, Any]:
        return {
            "whole_video": self.whole_video_checkbox.value,
            "start_time": self._clean_text(self.start_time_input.value),
            "end_option": self.end_option_radio.value,
            "end_time": self._clean_text(self.end_time_input.value),
            "re_encode": self.re_encode_checkbox.value,
            "crf": self._clean_text(self.crf_input.value),
            "preset": self.preset_dropdown.value,
            "quality": self.quality_dropdown.value,
            "format_choice": self.format_dropdown.value,
        }
