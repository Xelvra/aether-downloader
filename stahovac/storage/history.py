import json
import os
import threading
from datetime import datetime
from pathlib import Path

from stahovac.config.constants import HISTORY_FILE_NAME
from stahovac.utils.paths import get_base_dir


class HistoryManager:
    _lock = threading.Lock()

    @classmethod
    def load_history(cls) -> list[dict[str, str]]:
        with cls._lock:
            history_path = get_base_dir() / HISTORY_FILE_NAME
            items = cls._load_history_unsafe(history_path)
            existing = [item for item in items if item.get("file_path") and Path(item["file_path"]).is_file()]
            if len(existing) != len(items):
                cls._atomic_write(history_path, existing)
            return existing

    @classmethod
    def _load_history_unsafe(cls, history_path: Path) -> list[dict[str, str]]:
        if not history_path.exists():
            return []
        try:
            with open(history_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)][:30]
                return []
        except (OSError, json.JSONDecodeError):
            return []

    @classmethod
    def append(cls, title: str, url: str, file_path: str) -> None:
        history_path = get_base_dir() / HISTORY_FILE_NAME
        with cls._lock:
            history = cls._load_history_unsafe(history_path)
            history = [item for item in history if item.get("url") != url]
            new_entry = {
                "title": title,
                "url": url,
                "file_path": file_path,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            history.insert(0, new_entry)
            cls._atomic_write(history_path, history[:30])

    @classmethod
    def _atomic_write(cls, path: Path, data: list) -> None:
        temp_path = path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        except OSError:
            temp_path.unlink(missing_ok=True)
