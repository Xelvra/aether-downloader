from stahovac.config.constants import (
    COOKIES_FILE_OPTION,
    COOKIES_NONE,
    COOKIES_SOURCES,
    FORMAT_MP4,
    FORMAT_SUBS,
    FORMATS,
    QUALITY_BEST,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    CookieSource,
    MediaFormat,
)


class TestQuality:
    def test_quality_best(self):
        assert QUALITY_BEST == "Nejlepší dostupná"


class TestMediaFormat:
    def test_values(self):
        assert MediaFormat.MP4.value == "Video + audio (MP4)"
        assert MediaFormat.MP3.value == "Pouze zvuk (MP3)"
        assert MediaFormat.SUBS.value == "Pouze titulky (SRT)"

    def test_formats_list(self):
        assert [f.value for f in MediaFormat] == FORMATS
        assert FORMAT_MP4 == "Video + audio (MP4)"
        assert FORMAT_SUBS == "Pouze titulky (SRT)"


class TestCookieSource:
    def test_values(self):
        assert CookieSource.NONE.value == "Žádný (Bez cookies)"
        assert CookieSource.CHROME.value == "Chrome"
        assert CookieSource.FIREFOX.value == "Firefox"
        assert CookieSource.FILE.value == "Vlastní soubor (cookies.txt)"

    def test_cookies_sources_list(self):
        assert [c.value for c in CookieSource] == COOKIES_SOURCES
        assert COOKIES_NONE == "Žádný (Bez cookies)"
        assert COOKIES_FILE_OPTION == "Vlastní soubor (cookies.txt)"


class TestVideoExtensions:
    def test_common_formats(self):
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mkv" in VIDEO_EXTENSIONS
        assert ".webm" in VIDEO_EXTENSIONS
        assert ".avi" in VIDEO_EXTENSIONS

    def test_not_contains(self):
        assert ".pdf" not in VIDEO_EXTENSIONS
        assert ".txt" not in VIDEO_EXTENSIONS


class TestSubtitleExtensions:
    def test_common_formats(self):
        assert ".srt" in SUBTITLE_EXTENSIONS
        assert ".vtt" in SUBTITLE_EXTENSIONS

    def test_not_contains(self):
        assert ".pdf" not in SUBTITLE_EXTENSIONS
        assert ".mp4" not in SUBTITLE_EXTENSIONS
