import contextlib
import json
import os
from pathlib import Path
from typing import Any

from stahovac.config.app_config import AppConfig, migrate
from stahovac.config.constants import CONFIG_FILE_NAME
from stahovac.utils.paths import get_base_dir


class ConfigManager:
    """Ukládání/načítání config.json přes typovaný `AppConfig`.

    Načítání:
      1. neexistuje / poškozený JSON -> výchozí config
      2. chybějící klíče -> doplnit z výchozího
      3. špatné typy (re_encode, crf, preset, ...) -> opravit
      4. změněná verze schématu -> migrovat a uložit
    """

    @staticmethod
    def get_default_config() -> dict[str, Any]:
        cfg = AppConfig()
        cfg.output_folder = AppConfig._default_output_folder()
        return cfg.to_dict()

    @classmethod
    def load(cls) -> dict[str, Any]:
        config_path = get_base_dir() / CONFIG_FILE_NAME
        default_cfg = AppConfig.from_dict(cls.get_default_config())
        if not config_path.exists():
            cls._ensure_output_folder(default_cfg.output_folder)
            return default_cfg.to_dict()
        try:
            with open(config_path, encoding="utf-8") as f:
                raw_cfg = json.load(f)
            if not isinstance(raw_cfg, dict):
                cls.save(default_cfg.to_dict())
                cls._ensure_output_folder(default_cfg.output_folder)
                return default_cfg.to_dict()
            migrated = migrate(raw_cfg)
            loaded = AppConfig.from_storage(migrated)
            if _needs_fix(raw_cfg, loaded):
                cls.save(loaded.to_dict())
            cls._ensure_output_folder(loaded.output_folder)
            return loaded.to_dict()
        except (OSError, json.JSONDecodeError):
            cls.save(default_cfg.to_dict())
            cls._ensure_output_folder(default_cfg.output_folder)
            return default_cfg.to_dict()

    @staticmethod
    def _ensure_output_folder(folder: str) -> None:
        if not folder:
            return
        with contextlib.suppress(OSError):
            Path(folder).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save(config_data: dict[str, Any]) -> bool:
        config_path = get_base_dir() / CONFIG_FILE_NAME
        temp_path = config_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, config_path)
            return True
        except OSError:
            temp_path.unlink(missing_ok=True)
            return False


def _needs_fix(raw: dict[str, Any], loaded: AppConfig) -> bool:
    """True, pokud se načtená hodnota liší od surových dat (chyběly klíče / špatný typ / migrace)."""
    normalized = loaded.to_dict()
    for key in normalized:
        if key not in raw:
            return True
        raw_value = raw[key]
        if isinstance(raw_value, (dict, list)) or raw_value is None:
            return True
        if normalized[key] != raw_value:
            return True
    return False
