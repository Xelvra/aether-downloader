import re
from urllib.parse import urlparse

RE_PROGRESS = re.compile(
    r"\[download\]\s+(?P<percent>\d+\.?\d*)%\s+of\s+.*?\s+at\s+(?P<speed>.+?)\s+ETA\s+(?P<eta>\S+)"
)

RE_TIME_FORMAT = re.compile(r"^(?:\d+[,:]){0,2}\d+$")


def normalize_time(value: str) -> str:
    return value.replace(",", ":")


def pad_time(value: str) -> str:
    parts = normalize_time(value).split(":")
    if len(parts) == 1:
        return f"00:00:{parts[0].zfill(2)}"
    if len(parts) == 2:
        return f"00:{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"


def time_to_seconds(value: str) -> int:
    parts = normalize_time(value).split(":")
    if len(parts) == 1:
        return int(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def validate_time_range(start_raw: str, end_raw: str, end_option: str) -> str | None:
    if not RE_TIME_FORMAT.match(normalize_time(start_raw)):
        return "⚠️ Neplatný formát času „Začátek ořezu“ – použij SS, MM:SS nebo HH:MM:SS (např. 00:10:00)."
    if end_option != "Do konce videa":
        if not RE_TIME_FORMAT.match(normalize_time(end_raw)):
            return "⚠️ Neplatný formát času „Konec ořezu“ – použij SS, MM:SS nebo HH:MM:SS (např. 00:20:00)."
        start_sec = time_to_seconds(start_raw)
        end_sec = time_to_seconds(end_raw)
        if start_sec >= end_sec:
            return "⚠️ Konec ořezu musí být větší než začátek ořezu."
    return None


def validate_crf(value: str) -> str | None:
    try:
        crf = int(value)
    except (TypeError, ValueError):
        return "⚠️ Neplatná hodnota CRF – zadej celé číslo 0–51 (nižší = lepší kvalita)."
    if not 0 <= crf <= 51:
        return "⚠️ CRF musí být v rozsahu 0–51 (nižší = lepší kvalita)."
    return None


def is_valid_url(url: str) -> bool:
    if not url or not url.strip():
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
