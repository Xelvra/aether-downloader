from typing import Any

from stahovac.config.app_config import AppConfig


class AppState:
    """Stav aplikace – drží typovanou konfiguraci.

    Životní cyklus stahování sleduje `DownloadManager.download_state`
    (`stahovac.models.DownloadState`), nikoli boolean `is_downloading`.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def update_config_from_ui(
        self,
        quality: str,
        fmt: str,
        output_folder: str,
        cookies_source: str,
        cookies_file_path: str,
        re_encode: bool = False,
        crf: str = "23",
        preset: str = "fast",
    ) -> None:
        normalized = AppConfig.from_dict(
            {
                "quality": quality,
                "format": fmt,
                "output_folder": output_folder,
                "cookies_source": cookies_source,
                "cookies_file_path": cookies_file_path,
                "re_encode": re_encode,
                "crf": crf,
                "preset": preset,
            }
        )
        self.config.update(normalized.to_dict())
