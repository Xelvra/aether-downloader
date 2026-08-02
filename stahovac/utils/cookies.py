from pathlib import Path
from urllib.parse import urlparse

from stahovac.config.constants import COOKIES_FILE_OPTION, COOKIES_NONE


def _is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "youtube.com" or host.endswith(".youtube.com") or host == "youtu.be"


def resolve_cookies_opts(config: dict, url: str = "") -> dict:
    cookies_src = config.get("cookies_source", COOKIES_NONE)
    cookies_file = config.get("cookies_file_path", "")
    opts: dict = {}

    if cookies_src == COOKIES_NONE:
        return opts
    if url and _is_youtube(url):
        return opts
    if cookies_src == COOKIES_FILE_OPTION:
        if cookies_file and Path(cookies_file).is_file():
            opts["cookiefile"] = cookies_file
    else:
        opts["cookiesfrombrowser"] = (cookies_src.lower(),)

    return opts


def validate_cookies_file(path: str) -> str | None:
    """Vrátí chybovou hlášku, pokud soubor s cookies chybí nebo má nečekaný formát."""
    if not path:
        return "vyber soubor cookies.txt."
    p = Path(path)
    if not p.exists() or not p.is_file():
        return "soubor neexistuje."
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) >= 6:
                    return None
                return "soubor nemá očekávaný formát cookies.txt (pole oddělená tabulátory)."
        return "soubor neobsahuje žádné cookies."
    except OSError:
        return "soubor nelze otevřít."


def _safari_cookie_paths() -> list[Path]:
    home = Path.home()
    return [
        home / "Library" / "Cookies" / "Cookies.binarycookies",
        home / "Library" / "Containers" / "com.apple.Safari" / "Data" / "Library" / "Cookies" / "Cookies.binarycookies",
    ]


def safari_cookies_readable() -> tuple[bool, str]:
    """Zkontroluje čitelnost Safari cookies na macOS.

    Databázi Safari cookies chrání na macOS TCC – bez „Plného přístupu k disku“
    aplikace soubor sice vidí, ale otevřít ho nesmí (PermissionError), takže
    sub-only videa na Kicku/Twitchi končí jako „not found“. Vrací (čitelnost,
    zpráva), aby aplikace mohla uživatele nasměrovat.
    """
    for path in _safari_cookie_paths():
        if path.is_file():
            try:
                with open(path, "rb") as f:
                    f.read(64)
                return True, ""
            except OSError:
                return False, (
                    "Safari cookies se nepodařilo přečíst – povol aplikaci "
                    "„Plný přístup k disku“ (Systémové nastavení → Soukromí a zabezpečení) "
                    "a aplikaci restartuj, nebo vyber Chrome/Firefox nebo cookies.txt."
                )
    return False, (
        "Databáze cookies Safari nebyla nalezena – přihlas se na kick.com v Safari "
        "a aplikaci restartuj, nebo vyber Chrome/Firefox nebo cookies.txt."
    )
