from stahovac.config.constants import COOKIES_FILE_OPTION, COOKIES_NONE
from stahovac.utils.cookies import resolve_cookies_opts, validate_cookies_file


class TestResolveCookiesOpts:
    def test_no_cookies(self):
        config = {"cookies_source": COOKIES_NONE}
        assert resolve_cookies_opts(config) == {}

    def test_cookies_file_with_path(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        config = {"cookies_source": COOKIES_FILE_OPTION, "cookies_file_path": str(cookie_file)}
        result = resolve_cookies_opts(config)
        assert result == {"cookiefile": str(cookie_file)}

    def test_cookies_file_without_path(self):
        config = {"cookies_source": COOKIES_FILE_OPTION, "cookies_file_path": ""}
        assert resolve_cookies_opts(config) == {}

    def test_missing_cookie_file_ignored(self):
        config = {"cookies_source": COOKIES_FILE_OPTION, "cookies_file_path": "/nonexistent/cookies.txt"}
        assert resolve_cookies_opts(config) == {}

    def test_browser_chrome(self):
        config = {"cookies_source": "Chrome", "cookies_file_path": ""}
        result = resolve_cookies_opts(config)
        assert result == {"cookiesfrombrowser": ("chrome",)}

    def test_browser_firefox(self):
        config = {"cookies_source": "Firefox", "cookies_file_path": ""}
        result = resolve_cookies_opts(config)
        assert result == {"cookiesfrombrowser": ("firefox",)}

    def test_unknown_source(self):
        config = {"cookies_source": "Unknown", "cookies_file_path": ""}
        result = resolve_cookies_opts(config)
        assert result == {"cookiesfrombrowser": ("unknown",)}

    def test_skip_youtube_youtu_be(self):
        config = {"cookies_source": "Brave", "cookies_file_path": ""}
        result = resolve_cookies_opts(config, "https://youtu.be/GLdnKYWtBho")
        assert result == {}

    def test_skip_youtube_com(self):
        config = {"cookies_source": "Brave", "cookies_file_path": ""}
        result = resolve_cookies_opts(config, "https://www.youtube.com/watch?v=abcd")
        assert result == {}

    def test_youtube_in_subdomain(self):
        config = {"cookies_source": "Brave", "cookies_file_path": ""}
        result = resolve_cookies_opts(config, "https://m.youtube.com/watch?v=abcd")
        assert result == {}

    def test_youtube_token_in_query_is_not_youtube(self):
        config = {"cookies_source": "Brave", "cookies_file_path": ""}
        result = resolve_cookies_opts(config, "https://example.com/?next=youtube.com")
        assert result == {"cookiesfrombrowser": ("brave",)}

    def test_youtube_still_skipped_with_file_cookies(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        config = {"cookies_source": COOKIES_FILE_OPTION, "cookies_file_path": str(cookie_file)}
        result = resolve_cookies_opts(config, "https://youtu.be/abcd")
        assert result == {}

    def test_non_youtube_still_uses_cookies(self):
        config = {"cookies_source": "Brave", "cookies_file_path": ""}
        result = resolve_cookies_opts(config, "https://kick.com/video")
        assert result == {"cookiesfrombrowser": ("brave",)}


class TestValidateCookiesFile:
    def test_empty_path(self):
        assert validate_cookies_file("") is not None

    def test_missing_file(self):
        assert validate_cookies_file("/nonexistent/cookies.txt") is not None

    def test_valid_netscape_format(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text(
            "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tNAME\tVALUE\n",
            encoding="utf-8",
        )
        assert validate_cookies_file(str(cookie_file)) is None

    def test_wrong_format(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("just some text without tabs\n", encoding="utf-8")
        assert validate_cookies_file(str(cookie_file)) is not None

    def test_empty_file(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("", encoding="utf-8")
        assert validate_cookies_file(str(cookie_file)) is not None
