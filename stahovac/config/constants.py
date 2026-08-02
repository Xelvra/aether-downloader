from enum import Enum

APP_TITLE = "Aether Downloader"
APP_VERSION = "1.2.8"
VERSION_DISPLAY = f"v{APP_VERSION} Beta"
CONFIG_FILE_NAME = "config.json"
HISTORY_FILE_NAME = "history.json"
DOWNLOADS_DIR_NAME = "downloads"

QUALITY_BEST = "Nejlepší dostupná"


class MediaFormat(str, Enum):
    MP4 = "Video + audio (MP4)"
    MP3 = "Pouze zvuk (MP3)"
    SUBS = "Pouze titulky (SRT)"


FORMATS = [f.value for f in MediaFormat]


class CookieSource(str, Enum):
    NONE = "Žádný (Bez cookies)"
    CHROME = "Chrome"
    FIREFOX = "Firefox"
    EDGE = "Edge"
    BRAVE = "Brave"
    OPERA = "Opera"
    SAFARI = "Safari"
    FILE = "Vlastní soubor (cookies.txt)"


COOKIES_SOURCES = [c.value for c in CookieSource]
COOKIES_NONE = CookieSource.NONE.value
COOKIES_FILE_OPTION = CookieSource.FILE.value

FORMAT_MP4 = MediaFormat.MP4.value
FORMAT_SUBS = MediaFormat.SUBS.value

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts", ".3gp"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}
