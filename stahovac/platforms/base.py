"""Sdílené základy pro všechny platformy: společné HTTP hlavičky a výchozí opce."""

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def base_opts(url: str) -> dict:
    """Společné yt-dlp opce platné pro každou platformu.

    Přidávají se ke specifickým opcím platformy. Zde zatím prázdné – pokud
    bude potřeba něco univerzálního, přidej to sem (a ne do konkrétní platformy).
    """
    return {}
