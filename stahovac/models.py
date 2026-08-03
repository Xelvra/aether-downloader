from dataclasses import dataclass
from enum import Enum

from stahovac.config.constants import CRF_DEFAULT, END_OPTION_FULL, FORMAT_MP4, QUALITY_BEST


class DownloadState(str, Enum):
    """Jediný zdroj pravdy o životním cyklu stahování."""

    IDLE = "idle"
    FETCHING_METADATA = "fetching_metadata"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass
class VideoMetadata:
    title: str
    uploader: str
    duration: int
    thumbnail: str
    description: str
    available_resolutions: list[int] | None = None
    language: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "VideoMetadata":
        raw_duration = data.get("duration")
        return cls(
            title=data.get("title", "Neznámý název"),
            uploader=data.get("uploader", "Neznámý autor"),
            duration=int(raw_duration) if raw_duration is not None else 0,
            thumbnail=data.get("thumbnail", ""),
            description=data.get("description", ""),
            language=data.get("language"),
        )


@dataclass
class DownloadParams:
    """Typovaný kontrakt parametrů stahování (místo implicitního dictu)."""

    url: str = ""
    quality: str = QUALITY_BEST
    format_choice: str = FORMAT_MP4
    output_folder: str = ""
    whole_video: bool = True
    start_time: str = "00:00"
    end_time: str = "00:00"
    end_option: str = END_OPTION_FULL
    re_encode: bool = False
    crf: int = CRF_DEFAULT
    preset: str = "fast"

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadParams":
        def _int(key: str, default: int) -> int:
            try:
                return int(data.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            url=str(data.get("url", "")),
            quality=str(data.get("quality", QUALITY_BEST)),
            format_choice=str(data.get("format_choice", FORMAT_MP4)),
            output_folder=str(data.get("output_folder", "")),
            whole_video=bool(data.get("whole_video", True)),
            start_time=str(data.get("start_time", "00:00")),
            end_time=str(data.get("end_time", "00:00")),
            end_option=str(data.get("end_option", END_OPTION_FULL)),
            re_encode=bool(data.get("re_encode", False)),
            crf=_int("crf", CRF_DEFAULT),
            preset=str(data.get("preset", "fast")),
        )

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "quality": self.quality,
            "format_choice": self.format_choice,
            "output_folder": self.output_folder,
            "whole_video": self.whole_video,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "end_option": self.end_option,
            "re_encode": self.re_encode,
            "crf": self.crf,
            "preset": self.preset,
        }
