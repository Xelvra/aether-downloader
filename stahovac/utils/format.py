"""Formátování rychlosti a odhadu času pro uživatelské rozhraní."""


def format_speed(speed_bytes: float | None) -> str:
    if speed_bytes is None:
        return "–"
    if speed_bytes >= 1_000_000:
        return f"{speed_bytes / 1_000_000:.1f} MB/s"
    if speed_bytes >= 1_000:
        return f"{speed_bytes / 1_000:.0f} kB/s"
    return f"{speed_bytes:.0f} B/s"


def format_eta(eta_secs: float | None) -> str:
    if eta_secs is None:
        return "–"
    if eta_secs >= 3600:
        return f"{eta_secs / 3600:.0f}h {eta_secs % 3600 / 60:.0f}m"
    if eta_secs >= 60:
        return f"{eta_secs / 60:.0f}m {eta_secs % 60:.0f}s"
    return f"{eta_secs:.0f}s"
