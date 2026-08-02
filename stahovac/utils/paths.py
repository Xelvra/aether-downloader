import sys
from pathlib import Path

_BASE_DIR: Path | None = None


def set_base_dir(path: Path) -> None:
    global _BASE_DIR
    _BASE_DIR = path


def get_base_dir() -> Path:
    if _BASE_DIR is not None:
        return _BASE_DIR
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.absolute()
    return Path(__file__).resolve().parent.parent.parent
