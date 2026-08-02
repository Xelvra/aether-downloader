import flet as ft

SCREEN_WIDTH = 800
_FONT_SCALE = 1.4

BREAKPOINT_COMPACT = 500
BREAKPOINT_MEDIUM = 800
BREAKPOINT_MOBILE_NAV = 640


def set_screen_width(width: int) -> None:
    """Nastaví aktuální šířku obrazovky pro responsivní škálování."""
    global SCREEN_WIDTH
    SCREEN_WIDTH = int(width)


def scale_for(width: int) -> float:
    if width < BREAKPOINT_COMPACT:
        return max(0.8, width / BREAKPOINT_COMPACT)
    if width < BREAKPOINT_MEDIUM:
        return 1.2
    return 1.4


def _get_scale() -> float:
    return scale_for(SCREEN_WIDTH)


def sz(base: int) -> int:
    return int(base * _get_scale())


def sz_at(base: int, scale: float) -> int:
    return int(base * scale)


ICON_SIZE = sz(20)
ICON_SIZE_LARGE = sz(24)


COLOR_PRIMARY = "#4A90D9"
COLOR_ACCENT = "#64B5F6"
COLOR_SURFACE = "#1E1E2E"
COLOR_BG = "#161622"
COLOR_TEXT = "#E0E0F0"
COLOR_TEXT_SECONDARY = "#9090B0"
COLOR_SUCCESS = "#66BB6A"
COLOR_WARN = "#FFA726"

_BTN_PAD = 12


def action_button(icon, text, color, on_click):
    return ft.Button(
        content=ft.Row(
            [
                ft.Icon(icon, size=sz(22), color="#FFFFFF"),
                ft.Text(
                    text,
                    size=sz(14),
                    weight=ft.FontWeight.BOLD,
                    color="#FFFFFF",
                    expand=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        style=ft.ButtonStyle(
            bgcolor=color,
            shape=ft.RoundedRectangleBorder(radius=sz(8)),
            padding=ft.Padding(_BTN_PAD, _BTN_PAD, _BTN_PAD, _BTN_PAD),
        ),
        expand=True,
        on_click=on_click,
    )
