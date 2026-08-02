import platform
import subprocess
from pathlib import Path


def open_folder_in_explorer(path_str: str) -> bool:
    try:
        path = Path(path_str).resolve()
        if not path.exists():
            return False
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["explorer", str(path)])
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        return False
