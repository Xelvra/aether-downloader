"""Typovaný konfigurační model s validací a migrací.

Dříve byla konfigurace volný dict a položky `re_encode`, `crf`, `preset`
nebyly nijak validované. `AppConfig` garantuje typy při načtení z JSON.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stahovac.config.constants import (
    COOKIES_NONE,
    COOKIES_SOURCES,
    CRF_DEFAULT,
    DOWNLOADS_DIR_NAME,
    FORMAT_MP4,
    QUALITY_BEST,
    MediaFormat,
)
from stahovac.utils.paths import get_base_dir

SCHEMA_VERSION = 2
CRF_MIN = 0
CRF_MAX = 51
PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow")

_V1_FORMAT_TO_LABEL = {
    "mp4": MediaFormat.MP4.value,
    "mp3": MediaFormat.MP3.value,
    "srt": MediaFormat.SUBS.value,
}


def migrate(data: dict[str, Any] | None) -> dict[str, Any]:
    """Verzovaná migrace surové konfigurace z disku na aktuální schema.

    Zřetězená migrace: každá verze < aktuální provede svůj krok a posune
    `schema_version`. Místo pouhé normalizace se tím zachovává skutečná
    historie tvarů config.json.
    """
    raw = dict(data or {})
    version = _raw_version(raw)
    if version < 2:
        raw = _migrate_v1_to_v2(raw)
        version = 2
    raw["schema_version"] = version
    return raw


def _raw_version(data: dict[str, Any]) -> int:
    try:
        return int(data.get("schema_version", 1))
    except (TypeError, ValueError):
        return 1


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """v1 -> v2: surové tokeny formátu (``mp4``/``mp3``/``srt``) převést na
    zobrazované popisky roletky a doplnit klíče přidané ve v2."""
    fmt = data.get("format")
    if isinstance(fmt, str) and fmt in _V1_FORMAT_TO_LABEL:
        data["format"] = _V1_FORMAT_TO_LABEL[fmt]
    data.setdefault("re_encode", False)
    data.setdefault("crf", CRF_DEFAULT)
    data.setdefault("preset", "fast")
    return data


@dataclass
class AppConfig:
    quality: str = QUALITY_BEST
    format: str = FORMAT_MP4
    output_folder: str = ""
    cookies_source: str = COOKIES_NONE
    cookies_file_path: str = ""
    re_encode: bool = False
    crf: int = CRF_DEFAULT
    preset: str = "fast"
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality": self.quality,
            "format": self.format,
            "output_folder": self.output_folder,
            "cookies_source": self.cookies_source,
            "cookies_file_path": self.cookies_file_path,
            "re_encode": self.re_encode,
            "crf": self.crf,
            "preset": self.preset,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppConfig":
        """Typová koerce bez kontroly existence složky (používá se při ukládání z UI)."""
        data = data or {}
        output_folder = data.get("output_folder")
        if not isinstance(output_folder, str) or not output_folder:
            output_folder = cls._default_output_folder()
        cookies_source = data.get("cookies_source", COOKIES_NONE)
        if cookies_source not in COOKIES_SOURCES:
            cookies_source = COOKIES_NONE
        cookies_file = data.get("cookies_file_path")
        if not isinstance(cookies_file, str):
            cookies_file = ""
        preset = data.get("preset", "fast")
        if not isinstance(preset, str) or preset not in PRESETS:
            preset = "fast"
        return cls(
            quality=_coerce_str(data.get("quality"), QUALITY_BEST),
            format=_coerce_str(data.get("format"), FORMAT_MP4),
            output_folder=output_folder,
            cookies_source=cookies_source,
            cookies_file_path=cookies_file,
            re_encode=_coerce_bool(data.get("re_encode")),
            crf=_coerce_crf(data.get("crf")),
            preset=preset,
            schema_version=int(data.get("schema_version", 1)),
        )

    @classmethod
    def from_storage(cls, data: dict[str, Any] | None) -> "AppConfig":
        """Načtení z disku: navíc resetuje neexistující output_folder na výchozí."""
        cfg = cls.from_dict(data)
        if not cfg.output_folder or not Path(cfg.output_folder).exists():
            cfg.output_folder = cls._default_output_folder()
        return cfg

    @staticmethod
    def _default_output_folder() -> str:
        return str(get_base_dir() / DOWNLOADS_DIR_NAME)

    def __post_init__(self) -> None:
        self.crf = _coerce_crf(self.crf)
        self.re_encode = _coerce_bool(self.re_encode)
        if not isinstance(self.preset, str) or self.preset not in PRESETS:
            self.preset = "fast"
        if not isinstance(self.quality, str) or not self.quality:
            self.quality = QUALITY_BEST
        if not isinstance(self.format, str) or not self.format:
            self.format = FORMAT_MP4


def _coerce_str(value: Any, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ano", "on"}
    return False


def _coerce_crf(value: Any) -> int:
    try:
        crf = int(value)
    except (TypeError, ValueError):
        return CRF_DEFAULT
    if crf < CRF_MIN or crf > CRF_MAX:
        return CRF_DEFAULT
    return crf


# Backward compatible alias for code that referenced the constant name.
SCHEMA_VERSION_CURRENT = SCHEMA_VERSION
