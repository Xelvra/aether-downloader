import shutil
import sys
from pathlib import Path

from stahovac.config.constants import CONFIG_FILE_NAME, DOWNLOADS_DIR_NAME, HISTORY_FILE_NAME

_BASE_DIR: Path | None = None

APP_SUPPORT_DIR_NAME = "Application Support"
APP_DATA_DIR_NAME = "AetherDownloader"


def set_base_dir(path: Path) -> None:
    global _BASE_DIR
    _BASE_DIR = path


def get_frozen_base_dir() -> Path:
    """Base dir pro frozen (PyInstaller) aplikace.

    - macOS .app bundle → ``~/Library/Application Support/AetherDownloader``.
      Uživatelská data nesmí ležet uvnitř ``stahovac.app``: při aktualizaci by
      se ztratila a macOS soubory uvnitř app bundle nejde spolehlivě otevírat.
    - ostatní binárky (onefile/onedir) → adresář s executablem (přenosné).
    """
    exe = Path(sys.executable)
    in_bundle = (
        sys.platform == "darwin" and exe.parent.parent.name == "Contents" and exe.parent.parent.parent.suffix == ".app"
    )
    if in_bundle:
        return Path.home() / "Library" / APP_SUPPORT_DIR_NAME / APP_DATA_DIR_NAME
    return exe.parent.absolute()


def get_base_dir() -> Path:
    if _BASE_DIR is not None:
        return _BASE_DIR
    if getattr(sys, "frozen", False):
        return get_frozen_base_dir()
    return Path(__file__).resolve().parent.parent.parent


def migrate_bundle_data(target: Path) -> None:
    """Zajistí existenci cílového adresáře a přenese data z v1.2.4 (.app, kde
    ležela uvnitř bundle ``Contents/MacOS``) do nového umístění."""
    target.mkdir(parents=True, exist_ok=True)
    if not getattr(sys, "frozen", False):
        return
    exe = Path(sys.executable)
    old = exe.parent
    if old == target or not old.is_dir():
        return
    for name in (CONFIG_FILE_NAME, HISTORY_FILE_NAME, DOWNLOADS_DIR_NAME, "bin"):
        src = old / name
        dst = target / name
        if src.exists() and not dst.exists():
            try:
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            except OSError:
                pass
