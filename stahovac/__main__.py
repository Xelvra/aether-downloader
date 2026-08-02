import argparse
import os
import sys
from pathlib import Path

import flet as ft

from stahovac.platforms import patch_platform_extractors
from stahovac.utils.paths import get_frozen_base_dir, migrate_bundle_data, set_base_dir


def _noop():
    pass


def _configure_ssl() -> None:
    """Nasměruje TLS ověřování na certifi CA bundle.

    Binárka z PyInstalleru (hlavně z CI) nemá zaručený přístup k systémovému
    úložišti CA certifikátů. Proměnná ``SSL_CERT_FILE`` pak platí pro všechny
    defaultní SSL kontexty včetně těch, které vytváří yt-dlp; ``CURL_CA_BUNDLE``
    navíc pokrývá libcurl (curl_cffi). Obě se nastaví jen tehdy, když je
    certifi bundle součástí binárky (jinak se respektuje systémové nastavení).
    """
    if os.environ.get("SSL_CERT_FILE") and os.environ.get("CURL_CA_BUNDLE"):
        return
    bundle: str | None = None
    try:
        import certifi

        candidate = certifi.where()
    except (ImportError, OSError):
        candidate = None
    if candidate and os.path.isfile(candidate):
        bundle = candidate
    if bundle:
        os.environ.setdefault("SSL_CERT_FILE", bundle)
        os.environ.setdefault("CURL_CA_BUNDLE", bundle)


def _setup_runtime() -> None:
    """Inicializace běhového prostředí: patch yt-dlp, base dir, noop pip kontroly."""
    _configure_ssl()
    patch_platform_extractors()

    if getattr(sys, "frozen", False):
        base = get_frozen_base_dir()
        set_base_dir(base)
        migrate_bundle_data(base)
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


_SMOKE_HOSTS = ("https://www.google.com/", "https://github.com/")
_SMOKE_HOSTS_BEST_EFFORT = ("https://johnvansickle.com/ffmpeg/",)
_SMOKE_RETRIES = 3
_SMOKE_TIMEOUT = 15

_ANTI_BOT_MARKERS = (
    "sign in to confirm",
    "confirm you",
    "not a bot",
    "bot check",
    "http error 429",
    "http error 403",
    "too many requests",
    "rate.limit",
    "this video is unavailable",
    "geo",
)


def _run_checks(url: str | None, output: str | None) -> int:
    """Headless self-test binárky (TLS/CA + volitelně yt-dlp).

    Vrací 0, když vše prošlo, jinak 1. Výsledek se vypíše a (pokud je zadán
    ``output``) uloží jako JSON. Používá se hlavně v CI na zkompilované binárce,
    aby se odhalily problémy, které na běžném systému (např. s certifi CA
    bundlem) nevznikají.
    """
    import json
    import ssl
    import urllib.error
    import urllib.request

    from stahovac.utils.ssl import make_ssl_context

    results: list[dict] = []
    ok = True

    def record(name: str, success: bool, detail: str = "", fatal: bool = True) -> None:
        nonlocal ok
        results.append({"name": name, "ok": bool(success), "detail": detail})
        if not success and fatal:
            ok = False

    try:
        import certifi

        cafile = certifi.where()
        record("certifi-cafile", os.path.isfile(cafile), cafile)
    except Exception as exc:  # pragma: no cover
        record("certifi-cafile", False, f"{type(exc).__name__}: {exc}")

    def _check_host(host: str, fatal: bool) -> None:
        last_detail = "timeout"
        for _ in range(_SMOKE_RETRIES):
            req = urllib.request.Request(host, headers={"User-Agent": "AetherDownloader-selfcheck/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=_SMOKE_TIMEOUT, context=make_ssl_context()) as resp:
                    record(f"tls:{host}", True, f"HTTP {resp.status}", fatal=fatal)
                    return
            except urllib.error.HTTPError as exc:
                record(f"tls:{host}", True, f"HTTP {exc.code} (TLS OK)", fatal=fatal)
                return
            except (ssl.SSLCertVerificationError, ssl.SSLError, urllib.error.URLError) as exc:
                last_detail = f"{type(exc).__name__}: {exc}"
            except Exception as exc:  # pragma: no cover
                last_detail = f"{type(exc).__name__}: {exc}"
        record(f"tls:{host}", False, last_detail, fatal=fatal)

    for host in _SMOKE_HOSTS:
        _check_host(host, fatal=True)
    for host in _SMOKE_HOSTS_BEST_EFFORT:
        _check_host(host, fatal=False)

    if url:
        try:
            import yt_dlp

            opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "socket_timeout": 20,
                "retries": 2,
                "extractor_retries": 1,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            title = (info or {}).get("title") or "<bez názvu>"
            record("ytdlp-extract", True, title[:200])
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            low = text.lower()
            tolerated = any(m in low for m in _ANTI_BOT_MARKERS)
            record("ytdlp-extract", tolerated, text[:300])

    report = {"ok": ok, "results": results}
    if output:
        import contextlib

        with contextlib.suppress(OSError):
            Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


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
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run headless self-test of TLS/CA + yt-dlp connectivity and exit",
    )
    parser.add_argument(
        "--check-url",
        default=os.environ.get("AETHER_CHECK_URL"),
        help="URL ověřená přes yt-dlp v rámci --check (default: env AETHER_CHECK_URL)",
    )
    parser.add_argument(
        "--check-output",
        default=os.environ.get("AETHER_CHECK_OUTPUT"),
        help="Cesta k souboru, do kterého --check zapíše JSON výsledek (default: env AETHER_CHECK_OUTPUT)",
    )
    return parser.parse_args(argv)


def run(argv=None) -> None:
    _setup_runtime()
    args = parse_args(argv)

    if args.check:
        sys.exit(_run_checks(args.check_url, args.check_output))

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
