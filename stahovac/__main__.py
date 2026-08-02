import argparse
import os
import sys
from pathlib import Path

import flet as ft

from stahovac.platforms import patch_platform_extractors
from stahovac.utils.paths import set_base_dir


def _noop():
    pass


def _configure_ssl() -> None:
    """Nasměruje TLS ověřování na certifi CA bundle.

    Binárka z PyInstalleru (hlavně z CI) nemá zaručený přístup k systémovému
    úložišti CA certifikátů. Proměnná ``SSL_CERT_FILE`` pak platí pro všechny
    defaultní SSL kontexty včetně těch, které vytváří yt-dlp.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi

        bundle = certifi.where()
    except (ImportError, OSError):
        return
    if os.path.isfile(bundle):
        os.environ["SSL_CERT_FILE"] = bundle


def _setup_runtime() -> None:
    """Inicializace běhového prostředí: patch yt-dlp, base dir, noop pip kontroly."""
    _configure_ssl()
    patch_platform_extractors()

    if getattr(sys, "frozen", False):
        set_base_dir(Path(sys.executable).parent.absolute())
    else:
        set_base_dir(Path(__file__).resolve().parent.parent)

    try:
        import flet.utils.pip as _flet_pip

        _flet_pip.ensure_flet_desktop_package_installed = _noop
        _flet_pip.ensure_flet_web_package_installed = _noop
    except (ImportError, AttributeError):
        pass


def _is_headless() -> bool:
    """True, pokud běžíme bez grafického prostředí (jen Linux/BSD).

    Na Windows a macOS je grafické prostředí vždy přítomné a proměnné
    ``DISPLAY``/``WAYLAND_DISPLAY`` tam neexistují, takže se na nich
    headless detekce nikdy nespouští.
    """
    if sys.platform in ("win32", "darwin"):
        return False
    return not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aether Downloader")
    parser.add_argument(
        "--web",
        "-w",
        action="store_true",
        help="Force web server mode (start as HTTP server even if display is available)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("AETHER_HOST", "127.0.0.1"),
        help="Web server host (default: 127.0.0.1, env: AETHER_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AETHER_PORT", "8000")),
        help="Web server port (default: 8000, env: AETHER_PORT)",
    )
    return parser.parse_args(argv)


def run(argv=None) -> None:
    _setup_runtime()
    args = parse_args(argv)

    from stahovac.app import main

    if args.web or _is_headless():
        host = args.host
        port = args.port
        print("=" * 60)
        print("  Aether Downloader – webový server")
        print(f"  Aplikace běží na: http://{host}:{port}")
        print()
        print("  Otevři tento odkaz v prohlížeči na svém zařízení")
        print("  (nebo na jiném zařízení ve stejné síti).")
        print("=" * 60)
        ft.run(main=main, host=host, port=port, view=ft.AppView.WEB_BROWSER)
    else:
        ft.run(main=main)


def entry() -> None:
    run()


if __name__ == "__main__":
    run()
