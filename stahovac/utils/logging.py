"""Konfigurace standardního modulu `logging` pro technickou diagnostiku.

Aplikace má dva oddělené logovací kanály:

- **`on_log` callback** (Downloader → GUI Logs tab) – uživatelsky viditelné
  logy stahování,
- **modul `logging`** (`platforms/kick.py`, `core/metadata.py`,
  `utils/ssl.py`, `YtdlLogger` pro yt-dlp) – technická diagnostika.

Bez handleru se technická hlášení ztrácejí: defaultně Python zahazuje
`DEBUG`/`INFO` úplně a `WARNING`/`ERROR` posílá na `stderr`, který u
zabalené GUI aplikace (`console=False`) uživatel vůbec nevidí.
`configure_logging()` proto přidá `RotatingFileHandler` na `app.log`
do app-data adresáře, aby šlo při bug reportu dohledat, co se dělo.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_LOG_NAME = "app.log"
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 2


def configure_logging(base_dir: Path) -> None:
    """Přidá souborový handler na `app.log` do `base_dir`.

    - souborový handler na úrovni `DEBUG` (veškerá diagnostika jde do souboru),
    - `StreamHandler` na úrovni `WARNING` (console zůstává viditelná v terminálu).

    Volání je idempotentní (druhé volání nepřidá duplicitní handler) a
    best-effort – při chybě (např. nečitelný adresář) se tiše přeskočí,
    aplikace se nesmí kvůli logování zhroutit.
    """
    try:
        log_dir = Path(base_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / APP_LOG_NAME

        root = logging.getLogger()
        if not any(
            isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", None) == str(path)
            for h in root.handlers
        ):
            file_handler = RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            root.addHandler(file_handler)

        if not any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers
        ):
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.WARNING)
            stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            root.addHandler(stream_handler)

        root.setLevel(logging.DEBUG)
    except (OSError, ValueError):
        pass
