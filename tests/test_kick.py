from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from stahovac.platforms import kick


class TestParseVodUrl:
    def test_plain_url(self):
        assert kick.parse_vod_url("https://kick.com/channel/videos/abcd1234") == (
            "channel",
            "abcd1234",
        )

    def test_with_www(self):
        assert kick.parse_vod_url("https://www.kick.com/channel/videos/abcd1234") == (
            "channel",
            "abcd1234",
        )

    def test_trailing_slash(self):
        assert kick.parse_vod_url("https://kick.com/channel/videos/abcd1234/") == (
            "channel",
            "abcd1234",
        )

    def test_invalid_url(self):
        assert kick.parse_vod_url("https://youtube.com/watch?v=abc") is None

    def test_invalid_path(self):
        assert kick.parse_vod_url("https://kick.com/channel/not-videos/abcd") is None

    def test_empty_url(self):
        assert kick.parse_vod_url("") is None


class TestApiGet:
    def test_success_dict(self, monkeypatch):
        class FakeResp:
            def read(self):
                return b'{"ok": true}'

        monkeypatch.setattr(kick.urllib.request, "urlopen", lambda *a, **k: FakeResp())
        assert kick._api_get("v2/channels/x/videos") == {"ok": True}

    def test_success_list(self, monkeypatch):
        class FakeResp:
            def read(self):
                return b"[1, 2]"

        monkeypatch.setattr(kick.urllib.request, "urlopen", lambda *a, **k: FakeResp())
        assert kick._api_get("path") == [1, 2]

    def test_http_error(self, monkeypatch, caplog):
        def boom(*a, **k):
            raise HTTPError("url", 404, "Not Found", None, None)

        monkeypatch.setattr(kick.urllib.request, "urlopen", boom)
        assert kick._api_get("path") is None

    def test_generic_error(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(kick.urllib.request, "urlopen", boom)
        assert kick._api_get("path") is None

    def test_sends_authorization_header(self, monkeypatch):
        captured = {}

        class FakeResp:
            def read(self):
                return b"{}"

        def fake_urlopen(req, timeout=15, context=None):
            captured["headers"] = req.headers
            return FakeResp()

        monkeypatch.setattr(kick.urllib.request, "urlopen", fake_urlopen)
        kick._api_get("v1/video/xyz", auth_token="tok123")
        assert captured["headers"]["Authorization"] == "Bearer tok123"

    def test_cancel_error_from_urlopen_reraised(self, monkeypatch):
        def boom(*a, **k):
            raise kick._KickCancelError()

        monkeypatch.setattr(kick.urllib.request, "urlopen", boom)
        with pytest.raises(kick._KickCancelError):
            kick._api_get("v1/video/xyz")


class TestNormalizeV1Video:
    def test_missing_id_returns_none(self):
        assert kick._normalize_v1_video({"livestream": {"slug": "x"}}, "ch") is None

    def test_livestream_not_dict_returns_none(self):
        assert kick._normalize_v1_video({"livestream": []}, "ch") is None

    def test_valid_returns_normalized(self):
        resp = {
            "livestream": {"id": 7, "slug": "ch", "session_title": "T", "duration": 5000},
            "source": "https://media.example.com/x.m3u8",
            "views": 10,
        }
        result = kick._normalize_v1_video(resp, "ch")
        assert result is not None
        assert result["id"] == 7
        assert result["slug"] == "ch"
        assert result["duration"] == 5000


class TestFetchUrl:
    def test_success(self, monkeypatch):
        class FakeResp:
            def read(self):
                return b"hallo"

        monkeypatch.setattr(kick.urllib.request, "urlopen", lambda *a, **k: FakeResp())
        assert kick._fetch_url("https://example.com/playlist.m3u8") == "hallo"

    def test_error(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("boom")

        monkeypatch.setattr(kick.urllib.request, "urlopen", boom)
        assert kick._fetch_url("https://example.com/playlist.m3u8") is None

    def test_sends_authorization_header(self, monkeypatch):
        captured = {}

        class FakeResp:
            def read(self):
                return b"ok"

        def fake_urlopen(req, timeout=15, context=None):
            captured["headers"] = req.headers
            return FakeResp()

        monkeypatch.setattr(kick.urllib.request, "urlopen", fake_urlopen)
        kick._fetch_url("https://example.com/playlist.m3u8", auth_token="tok123")
        assert captured["headers"]["Authorization"] == "Bearer tok123"

    def test_cancel_error_from_urlopen_reraised(self, monkeypatch):
        def boom(*a, **k):
            raise kick._KickCancelError()

        monkeypatch.setattr(kick.urllib.request, "urlopen", boom)
        with pytest.raises(kick._KickCancelError):
            kick._fetch_url("https://example.com/playlist.m3u8")


def _mk_vod(uuid, vod_id, title="Some VOD"):
    return {
        "id": 123,
        "session_title": title,
        "slug": "some-vod",
        "video": {"id": 123, "uuid": uuid, "source": "https://media.example.com/playlist.m3u8"},
        "livestream": {"vod_id": vod_id},
    }


class TestFetchVodData:
    def test_matching_uuid(self, monkeypatch):
        monkeypatch.setattr(
            kick, "_api_get", lambda path, cancel_check=None: [_mk_vod("abc", "123"), _mk_vod("def", "456")]
        )
        result = kick.fetch_vod_data("https://kick.com/ch/videos/def")
        assert result is not None
        assert result["video"]["uuid"] == "def"

    def test_invalid_url(self, monkeypatch):
        assert kick.fetch_vod_data("https://youtube.com/watch?v=x") is None

    def test_non_list_response(self, monkeypatch):
        monkeypatch.setattr(kick, "_api_get", lambda path, cancel_check=None: {"not": "a list"})
        assert kick.fetch_vod_data("https://kick.com/ch/videos/abc") is None

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(kick, "_api_get", lambda path, cancel_check=None: [_mk_vod("abc", "123")])
        assert kick.fetch_vod_data("https://kick.com/ch/videos/zzz") is None

    def test_skips_non_dict_items(self, monkeypatch):
        monkeypatch.setattr(kick, "_api_get", lambda path, cancel_check=None: ["junk", _mk_vod("abc", "123")])
        result = kick.fetch_vod_data("https://kick.com/ch/videos/abc")
        assert result is not None
        assert result["video"]["uuid"] == "abc"

    def test_resolves_directly_with_auth(self, monkeypatch):
        calls = []

        def fake_get(path, cancel_check=None, auth_token=None):
            calls.append((path, auth_token))
            return {
                "id": 5,
                "source": "https://media.example.com/x.m3u8",
                "uuid": "the-uuid",
                "livestream": {
                    "id": 5,
                    "slug": "the-slug",
                    "session_title": "Sub VOD",
                    "duration": 1000,
                    "user": {"id": 1, "username": "streamer"},
                    "categories": [],
                },
            }

        monkeypatch.setattr(kick, "_api_get", fake_get)
        result = kick.fetch_vod_data("https://kick.com/ch/videos/the-uuid", auth_token="tok123")
        assert result is not None
        assert result["session_title"] == "Sub VOD"
        assert result["channel"] == "ch"
        assert calls == [("v1/video/the-uuid", "tok123")]

    def test_no_auth_uses_channel_list(self, monkeypatch):
        calls = []

        def fake_get(path, cancel_check=None):
            calls.append(path)
            return [_mk_vod("abc", "123")]

        monkeypatch.setattr(kick, "_api_get", fake_get)
        result = kick.fetch_vod_data("https://kick.com/ch/videos/abc")
        assert result is not None
        assert calls == ["v2/channels/ch/videos"]


class TestFetchVodPage:
    URL = "https://kick.com/aethercosmologyczsk/videos/019fb6ea-0d60-75ca-8756-11f0d8b1f817"
    M3U8 = (
        "https://fa723fc1b171.us-west-2.playback.live-video.net/api/video/v1/"
        "us-west-2.196233775518.channel.YNnlAxotHfyv.m3u8?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzM4NCJ9"
    )
    PAGE = (
        '<script>self.__next_f.push([1,"'
        r'\"category\":{\"id\":15,\"name\":\"Just Chatting\",\"slug\":\"just-chatting\"},'
        r'\"channel\":{\"id\":50494549,\"slug\":\"aethercosmologyczsk\",\"username\":\"AetherCosmologyczsk\"},'
        r'\"duration\":54543,\"end_time\":\"2026-07-31T21:54:21Z\",\"id\":\"019fb6ea-0d60-75ca-8756-11f0d8b1f817\",'
        r'\"is_live\":false,\"language\":\"cs\",\"status\":\"sub_only\",'
        r'\"thumbnail\":{\"src\":\"https://images.kick.com/thumb.webp\",\"srcSet\":\"https://images.kick.com/1080.webp 1920w\"},'
        r'\"title\":\"#156 Sub Only Stream\",\"viewer_count\":3214}'
        '"])</script>'
        '<script>var x="' + M3U8 + '"</script>'
    )

    def test_extracts_sub_only_vod(self, monkeypatch):
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: self.PAGE)
        result = kick._fetch_vod_page(self.URL)
        assert result is not None
        assert result["session_title"] == "#156 Sub Only Stream"
        assert result["duration"] == 54543000
        assert result["view_count"] == 3214
        assert result["language"] == "cs"
        assert result["categories"] == [{"name": "Just Chatting"}]
        assert result["channel"] == "aethercosmologyczsk"
        assert result["user"] == {"id": "50494549", "username": "AetherCosmologyczsk"}
        assert result["thumbnail"] == {"src": "https://images.kick.com/thumb.webp"}
        assert result["source"] == self.M3U8

    def test_invalid_url(self, monkeypatch):
        assert kick._fetch_vod_page("https://youtube.com/watch?v=x") is None

    def test_page_fetch_failure(self, monkeypatch):
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: None)
        assert kick._fetch_vod_page(self.URL) is None

    def test_no_m3u8(self, monkeypatch):
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: "<html>no token</html>")
        assert kick._fetch_vod_page(self.URL) is None

    def test_no_video_object(self, monkeypatch):
        page = "<html>https://cdn.example.com/x.m3u8?token=abc</html>"
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: page)
        assert kick._fetch_vod_page(self.URL) is None

    def test_no_playback_url_in_vod_region(self, monkeypatch):
        page = self.PAGE[: self.PAGE.index('"])</script>') + len('"])</script>')]
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: page)
        assert kick._fetch_vod_page(self.URL) is None

    LIVE_M3U8 = (
        "https://fa723fc1b171.us-west-2.playback.live-video.net/api/video/v1/"
        "us-west-2.196233775518.channel.YNnlAxotHfyv.m3u8?token=live-player"
    )

    def test_prefers_vod_m3u8_over_live_player(self, monkeypatch):
        page = (
            '<script>var x="' + self.LIVE_M3U8 + '"</script>'
            + self.PAGE
            + '<script>var y="' + self.M3U8 + '"</script>'
        )
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: page)
        result = kick._fetch_vod_page(self.URL)
        assert result is not None
        assert result["source"] == self.M3U8

    def test_forwards_auth_token_to_fetch_url(self, monkeypatch):
        seen = {}

        def fake_fetch(url, cancel_check=None, auth_token=None):
            seen["token"] = auth_token
            return self.PAGE

        monkeypatch.setattr(kick, "_fetch_url", fake_fetch)
        kick._fetch_vod_page(self.URL, auth_token="tok123")
        assert seen["token"] == "tok123"


class TestResolveVodId:
    def test_full_resolution(self, monkeypatch):
        vods = [
            {
                "id": 1,
                "video": {"uuid": "uuid-1", "source": ""},
            }
        ]
        detail = {
            "id": 99,
            "uuid": "uuid-1",
            "source": "https://media.example.com/stream.m3u8",
            "views": 42,
            "livestream": {
                "vod_id": "abc",
                "id": 7,
                "slug": "ch",
                "session_title": "VOD Title",
                "duration": 1234,
                "language": "cs",
                "thumbnail": {"src": "https://example.com/t.jpg"},
                "categories": [{"name": "Games"}],
                "user": {"username": "streamer"},
            },
        }

        def fake_get(path, cancel_check=None):
            if path.startswith("v2/channels/"):
                return vods
            if path.startswith("v1/video/"):
                return detail
            raise AssertionError(f"unexpected path {path}")

        monkeypatch.setattr(kick, "_api_get", fake_get)
        result = kick._resolve_vod_id("https://kick.com/ch/videos/abc")
        assert result is not None
        assert result["id"] == 7
        assert result["slug"] == "ch"
        assert result["source"] == "https://media.example.com/stream.m3u8"
        assert result["video"]["uuid"] == "uuid-1"
        assert result["view_count"] == 42

    def test_no_vods(self, monkeypatch):
        monkeypatch.setattr(kick, "_api_get", lambda path, cancel_check=None: [])
        assert kick._resolve_vod_id("https://kick.com/ch/videos/abc") is None

    def test_detail_not_dict(self, monkeypatch):
        monkeypatch.setattr(
            kick,
            "_api_get",
            lambda path, cancel_check=None: [{"id": 1, "video": {"uuid": "u1"}}] if path.startswith("v2") else "junk",
        )
        assert kick._resolve_vod_id("https://kick.com/ch/videos/abc") is None

    def test_vod_id_never_matches(self, monkeypatch):
        monkeypatch.setattr(
            kick,
            "_api_get",
            lambda path, cancel_check=None: (
                [{"id": 1, "video": {"uuid": "u1"}}] if path.startswith("v2") else {"livestream": {"vod_id": "other"}}
            ),
        )
        assert kick._resolve_vod_id("https://kick.com/ch/videos/abc") is None

    def test_invalid_url(self, monkeypatch):
        assert kick._resolve_vod_id("https://example.com/") is None

    def test_forwards_auth_token(self, monkeypatch):
        calls = []

        def fake_get(path, cancel_check=None, auth_token=None):
            calls.append((path, auth_token))
            if path.startswith("v2/channels/"):
                return [{"id": 1, "video": {"uuid": "u1"}}]
            return {"livestream": {"vod_id": "abc", "id": 1, "slug": "s", "session_title": "T", "categories": []}}

        monkeypatch.setattr(kick, "_api_get", fake_get)
        result = kick._resolve_vod_id("https://kick.com/ch/videos/abc", auth_token="tok123")
        assert result is not None
        assert calls == [
            ("v2/channels/ch/videos", "tok123"),
            ("v1/video/u1", "tok123"),
        ]

    def test_skips_non_dict_and_missing_uuid(self, monkeypatch):
        vods = [
            "junk",
            {"id": 1, "video": {}},
            {"id": 2, "video": {"uuid": "u2"}},
        ]

        def fake_get(path, cancel_check=None):
            if path.startswith("v2/channels/"):
                return vods
            return {
                "id": 99,
                "uuid": "u2",
                "source": "https://media.example.com/s.m3u8",
                "views": 3,
                "livestream": {"vod_id": "abc", "id": 7, "slug": "ch", "session_title": "T", "duration": 0, "categories": []},
            }

        monkeypatch.setattr(kick, "_api_get", fake_get)
        result = kick._resolve_vod_id("https://kick.com/ch/videos/abc")
        assert result is not None
        assert result["id"] == 7


class TestMakeFormat:
    def test_video_format(self):
        fmt = kick._make_format(
            "https://m.example.com/1080p.m3u8", "https://m.example.com/master.m3u8", 1080, 1920, 4_000_000
        )
        assert fmt["height"] == 1080
        assert fmt["width"] == 1920
        assert fmt["vcodec"] == "h264"
        assert fmt["format_id"] == "hls-1080"
        assert fmt["tbr"] == 4000
        assert fmt["fragment_base_url"] == "https://m.example.com/"

    def test_audio_format(self):
        fmt = kick._make_format(
            "https://m.example.com/audio.m3u8",
            "https://m.example.com/master.m3u8",
            None,
            None,
            128_000,
            is_audio_only=True,
        )
        assert fmt["vcodec"] == "none"
        assert fmt["acodec"] == "aac"
        assert fmt["format_id"] == "hls-128000"
        assert fmt["height"] is None

    def test_no_height_no_bandwidth(self):
        fmt = kick._make_format("https://m.example.com/x.m3u8", "https://m.example.com/master.m3u8", None, None, None)
        assert fmt["format_id"] == "hls"
        assert fmt["tbr"] is None

    def test_http_headers_copied(self):
        fmt = kick._make_format("u", "m", 720, 1280, 1)
        assert fmt["http_headers"]["Referer"] == "https://kick.com/"

    def test_authorization_header_added(self):
        fmt = kick._make_format("u", "m", 720, 1280, 1, auth_token="tok123")
        assert fmt["http_headers"]["Authorization"] == "Bearer tok123"


class TestParseMasterPlaylist:
    MASTER = (
        "#EXTM3U\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1280x720,CODECS="avc1.4d401f,mp4a.40.2"\n'
        "720p.m3u8\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2"\n'
        "https://cdn.example.com/1080p.m3u8\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=128000,CODECS="mp4a.40.2"\n'
        "audio.m3u8\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="Czech"\n'
    )

    def test_parses_variants(self):
        formats = kick._parse_master_playlist(self.MASTER, "https://cdn.example.com/master.m3u8")
        assert len(formats) == 3

        video = formats[0]
        assert video["height"] == 720
        assert video["width"] == 1280
        assert video["tbr"] == 1280
        assert video["url"] == "https://cdn.example.com/720p.m3u8"
        assert video["vcodec"] == "h264"

    def test_absolute_url_kept(self):
        formats = kick._parse_master_playlist(self.MASTER, "https://cdn.example.com/master.m3u8")
        assert formats[1]["url"] == "https://cdn.example.com/1080p.m3u8"

    def test_audio_only_detected(self):
        formats = kick._parse_master_playlist(self.MASTER, "https://cdn.example.com/master.m3u8")
        audio = formats[2]
        assert audio["vcodec"] == "none"
        assert audio["acodec"] == "aac"

    def test_empty_content(self):
        assert kick._parse_master_playlist("", "https://cdn.example.com/master.m3u8") == []

    def test_malformed_attributes_do_not_crash(self):
        playlist = (
            '#EXT-X-STREAM-INF:BANDWIDTH=NaN,RESOLUTION=abcx,CODECS="avc1"\n'
            "https://cdn.example.com/variant.m3u8\n"
            '#EXT-X-STREAM-INF:BANDWIDTH=1000,RESOLUTION=1280x720,CODECS="avc1"\n'
            "https://cdn.example.com/ok.m3u8\n"
        )
        formats = kick._parse_master_playlist(playlist, "https://cdn.example.com/master.m3u8")
        assert len(formats) == 2
        assert formats[0]["height"] is None
        assert formats[0]["tbr"] is None
        assert formats[1]["height"] == 720
        assert formats[1]["tbr"] == 1

    def test_skips_comments_and_blanks_between_stream_inf_and_uri(self):
        playlist = (
            "#EXTM3U\n"
            '#EXT-X-STREAM-INF:BANDWIDTH=1000,RESOLUTION=640x360\n'
            "# a comment\n"
            "\n"
            "360p.m3u8\n"
        )
        formats = kick._parse_master_playlist(playlist, "https://cdn.example.com/master.m3u8")
        assert len(formats) == 1
        assert formats[0]["height"] == 360


class TestBuildHlsFormats:
    def test_empty_source(self, monkeypatch):
        assert kick._build_hls_formats("") == []

    def test_playlist_fetch_failure_falls_back(self, monkeypatch):
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: None)
        formats = kick._build_hls_formats("https://media.example.com/x.m3u8")
        assert len(formats) == 1
        assert formats[0]["height"] == 1080

    def test_master_playlist(self, monkeypatch):
        master = '#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720,CODECS="avc1,mp4a"\n720p.m3u8\n'
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: master)
        formats = kick._build_hls_formats("https://media.example.com/master.m3u8")
        assert len(formats) == 1
        assert formats[0]["height"] == 720

    def test_media_playlist_falls_back(self, monkeypatch):
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: "#EXTM3U\n#EXTINF:5,\nseg.ts\n")
        formats = kick._build_hls_formats("https://media.example.com/media.m3u8")
        assert len(formats) == 1

    def test_master_without_variants_falls_back(self, monkeypatch):
        monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: "#EXT-X-STREAM-INF:BANDWIDTH=1000\n")
        formats = kick._build_hls_formats("https://media.example.com/master.m3u8")
        assert len(formats) == 1
        assert formats[0]["height"] == 1080

    def test_passes_auth_token_to_fetch(self, monkeypatch):
        seen = {}

        def fake_fetch(url, cancel_check=None, auth_token=None):
            seen["token"] = auth_token
            return None

        monkeypatch.setattr(kick, "_fetch_url", fake_fetch)
        formats = kick._build_hls_formats("https://media.example.com/x.m3u8", auth_token="tok123")
        assert seen["token"] == "tok123"
        assert formats[0]["http_headers"]["Authorization"] == "Bearer tok123"


class TestBuildYtdlpInfo:
    def _full_vod(self):
        return {
            "id": 42,
            "session_title": "Great Stream",
            "slug": "great-stream",
            "source": "",
            "duration": 3_600_000,
            "language": "cs",
            "views": 99,
            "thumbnail": {"src": "https://example.com/t.jpg"},
            "categories": [{"name": "Games"}, {"slug": "music"}],
            "user": {"id": 5, "username": "streamer"},
            "channel": "channel-slug",
            "channel_id": 7,
            "video": {"id": 42, "source": "https://media.example.com/playlist.m3u8"},
        }

    def test_full_info(self, monkeypatch):
        monkeypatch.setattr(kick, "_build_hls_formats", lambda source, cancel_check=None: [{"format_id": "hls-1080"}])
        info = kick.build_ytdlp_info(self._full_vod())
        assert info["id"] == "42"
        assert info["title"] == "Great Stream"
        assert info["uploader"] == "streamer"
        assert info["uploader_id"] == "5"
        assert info["channel"] == "channel-slug"
        assert info["duration"] == 3600
        assert info["thumbnail"] == "https://example.com/t.jpg"
        assert info["view_count"] == 99
        assert info["categories"] == ["Games", "music"]
        assert info["formats"] == [{"format_id": "hls-1080"}]

    def test_thumbnail_as_string(self, monkeypatch):
        monkeypatch.setattr(kick, "_build_hls_formats", lambda source, cancel_check=None: [])
        vod = self._full_vod()
        vod["thumbnail"] = "https://example.com/plain.jpg"
        info = kick.build_ytdlp_info(vod)
        assert info["thumbnail"] == "https://example.com/plain.jpg"

    def test_empty_vod(self, monkeypatch):
        monkeypatch.setattr(kick, "_build_hls_formats", lambda source, cancel_check=None: [])
        info = kick.build_ytdlp_info({})
        assert info["title"] == "Unknown"
        assert info["uploader"] == ""
        assert info["duration"] == 0
        assert info["formats"] == []

    def test_categories_strings(self, monkeypatch):
        monkeypatch.setattr(kick, "_build_hls_formats", lambda source, cancel_check=None: [])
        vod = self._full_vod()
        vod["categories"] = ["a", "b"]
        info = kick.build_ytdlp_info(vod)
        assert info["categories"] == ["a", "b"]

    def test_auth_token_passed_to_formats(self, monkeypatch):
        seen = {}

        def fake_build(source, cancel_check=None, auth_token=None):
            seen["token"] = auth_token
            return []

        monkeypatch.setattr(kick, "_build_hls_formats", fake_build)
        kick.build_ytdlp_info(self._full_vod(), auth_token="tok123")
        assert seen["token"] == "tok123"


class TestKickAdapter:
    def test_supports_kick_vod(self):
        assert kick.KickAdapter.supports("https://kick.com/ch/videos/abc") is True

    def test_not_supported_other(self):
        assert kick.KickAdapter.supports("https://www.twitch.tv/videos/1") is False

    def test_extract_uses_fetch_vod_data(self, monkeypatch):
        called = []

        def fake_fetch(url, cancel_check=None):
            called.append(url)
            return {"session_title": "T", "slug": "s", "source": "", "duration": 0, "categories": []}

        monkeypatch.setattr(kick, "fetch_vod_data", fake_fetch)
        monkeypatch.setattr(kick, "_build_hls_formats", lambda source, cancel_check=None: [])
        result = kick.KickAdapter.extract("https://kick.com/ch/videos/abc")
        assert result is not None
        assert result["title"] == "T"
        assert called == ["https://kick.com/ch/videos/abc"]

    def test_extract_falls_back_to_resolve(self, monkeypatch):
        monkeypatch.setattr(kick, "fetch_vod_data", lambda url, cancel_check=None: None)
        monkeypatch.setattr(kick, "_fetch_vod_page", lambda url, cancel_check=None: None)

        def fake_resolve(url, cancel_check=None):
            return {"session_title": "Resolved", "slug": "s", "source": "", "duration": 0, "categories": []}

        monkeypatch.setattr(kick, "_resolve_vod_id", fake_resolve)
        monkeypatch.setattr(kick, "_build_hls_formats", lambda source, cancel_check=None: [])
        result = kick.KickAdapter.extract("https://kick.com/ch/videos/abc")
        assert result["title"] == "Resolved"

    def test_extract_uses_page_scrape(self, monkeypatch):
        monkeypatch.setattr(kick, "fetch_vod_data", lambda url, cancel_check=None: None)

        def fake_page(url, cancel_check=None):
            return {
                "session_title": "Page VOD",
                "slug": "page",
                "source": "https://cdn.example.com/x.m3u8",
                "duration": 0,
                "categories": [],
            }

        monkeypatch.setattr(kick, "_fetch_vod_page", fake_page)
        monkeypatch.setattr(kick, "_build_hls_formats", lambda source, cancel_check=None: [])
        result = kick.KickAdapter.extract("https://kick.com/ch/videos/abc")
        assert result["title"] == "Page VOD"

    def test_extract_returns_none_when_unresolved(self, monkeypatch):
        monkeypatch.setattr(kick, "fetch_vod_data", lambda url, cancel_check=None: None)
        monkeypatch.setattr(kick, "_fetch_vod_page", lambda url, cancel_check=None: None)
        monkeypatch.setattr(kick, "_resolve_vod_id", lambda url, cancel_check=None: None)
        assert kick.KickAdapter.extract("https://kick.com/ch/videos/abc") is None


class TestSessionTokenFromExtractor:
    @staticmethod
    def _cookies(token=None):
        from http.cookies import SimpleCookie

        jar = SimpleCookie()
        if token is not None:
            jar["session_token"] = token
        return jar

    def test_reads_and_unquotes_session_token(self):
        extractor = SimpleNamespace()
        extractor._get_cookies = lambda url: self._cookies("secret%20token")
        assert kick._session_token_from_extractor(extractor) == "secret token"

    def test_no_cookie(self):
        extractor = SimpleNamespace()
        extractor._get_cookies = lambda url: self._cookies()
        assert kick._session_token_from_extractor(extractor) is None

    def test_returns_none_on_error(self):
        def boom(url):
            raise RuntimeError("no cookies")

        extractor = SimpleNamespace()
        extractor._get_cookies = boom
        assert kick._session_token_from_extractor(extractor) is None


class TestCheckYtdlpVersion:
    def test_current_version_no_warning(self, monkeypatch, caplog):
        monkeypatch.setattr("yt_dlp.version.__version__", "2026.07.04")
        with caplog.at_level("WARNING"):
            kick._check_ytdlp_version()
        assert not [r for r in caplog.records if "below tested version" in r.message]

    def test_old_version_warns(self, monkeypatch, caplog):
        monkeypatch.setattr("yt_dlp.version.__version__", "2023.01.01")
        with caplog.at_level("WARNING"):
            kick._check_ytdlp_version()
        assert any("below tested version" in r.message for r in caplog.records)

    def test_invalid_version_no_error(self, monkeypatch):
        monkeypatch.setattr("yt_dlp.version.__version__", "not-a-version")
        kick._check_ytdlp_version()  # should not raise

    def test_installed_version_within_supported_range(self):
        from yt_dlp.version import __version__

        major, minor = (int(p) for p in __version__.split(".")[:2])
        assert (major, minor) >= (2024, 12), "Nainstalovaný yt-dlp je starší než podporovaná verze"
        assert major < 2027, (
            "Nainstalovaný yt-dlp je mimo podporovaný rozsah – aktualizuj horní hranici v pyproject.toml"
        )


class TestPatchYtdlpExtractor:
    def test_import_failure_is_swallowed(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yt_dlp.extractor.kick":
                raise ImportError("no kick extractor")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        kick.patch_ytdlp_extractor()  # should not raise

    def test_patch_applies_and_fallback_works(self, monkeypatch):
        from yt_dlp.extractor.kick import KickVODIE

        orig_valid_url = KickVODIE._VALID_URL
        orig_real_extract = KickVODIE._real_extract
        orig_fetch_vod = kick.fetch_vod_data
        orig_resolve = kick._resolve_vod_id

        try:
            monkeypatch.setattr(kick, "_fetch_url", lambda url, cancel_check=None: None)
            kick.patch_ytdlp_extractor()

            assert KickVODIE._VALID_URL == r"https?://(?:www\.)?kick\.com/[\w-]+/videos/(?P<id>[\w-]+)"
            assert KickVODIE._real_extract.__name__ == "_patched_extract"

            monkeypatch.setattr(
                kick,
                "fetch_vod_data",
                lambda url, cancel_check=None: {
                    "id": 1,
                    "session_title": "Fallback",
                    "slug": "fallback",
                    "source": "",
                    "duration": 0,
                    "user": {"username": "streamer"},
                    "categories": [],
                },
            )

            class FakeSelf:
                def _match_id(self, url):
                    return "abcd"

                def _call_api(self, *a, **k):
                    raise RuntimeError("api dead")

            result = KickVODIE._real_extract(FakeSelf(), "https://kick.com/ch/videos/abcd")
            assert result["title"] == "Fallback"
            assert result["id"] == "1"
        finally:
            KickVODIE._VALID_URL = orig_valid_url
            KickVODIE._real_extract = orig_real_extract
            kick.fetch_vod_data = orig_fetch_vod
            kick._resolve_vod_id = orig_resolve

    def test_patch_raises_extractor_error_when_not_found(self, monkeypatch):
        from yt_dlp.extractor.kick import KickVODIE
        from yt_dlp.utils import ExtractorError

        orig_valid_url = KickVODIE._VALID_URL
        orig_real_extract = KickVODIE._real_extract
        orig_fetch_vod = kick.fetch_vod_data
        orig_resolve = kick._resolve_vod_id

        try:
            kick.patch_ytdlp_extractor()
            monkeypatch.setattr(kick, "fetch_vod_data", lambda url, cancel_check=None: None)
            monkeypatch.setattr(kick, "_fetch_vod_page", lambda url, cancel_check=None: None)
            monkeypatch.setattr(kick, "_resolve_vod_id", lambda url, cancel_check=None: None)

            class FakeSelf:
                def _match_id(self, url):
                    return "abcd"

                def _call_api(self, *a, **k):
                    raise RuntimeError("api dead")

            with pytest.raises(ExtractorError):
                KickVODIE._real_extract(FakeSelf(), "https://kick.com/ch/videos/abcd")
        finally:
            KickVODIE._VALID_URL = orig_valid_url
            KickVODIE._real_extract = orig_real_extract
            kick.fetch_vod_data = orig_fetch_vod
            kick._resolve_vod_id = orig_resolve


class TestKickCancel:
    def test_api_get_cancel_raises(self):
        with pytest.raises(kick._KickCancelError):
            kick._api_get("v2/channels/x/videos", cancel_check=lambda: True)

    def test_fetch_url_cancel_raises(self):
        with pytest.raises(kick._KickCancelError):
            kick._fetch_url("https://example.com/x.m3u8", cancel_check=lambda: True)

    def test_fetch_vod_data_aborts_after_cancel(self):
        with pytest.raises(kick._KickCancelError):
            kick.fetch_vod_data("https://kick.com/ch/videos/abc", cancel_check=lambda: True)

    def test_resolve_vod_id_aborts_mid_loop(self, monkeypatch):
        vods = [{"id": i, "video": {"uuid": f"u{i}"}} for i in range(20)]
        monkeypatch.setattr(kick, "_api_get", lambda path, cancel_check=None: vods)
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] >= 2

        with pytest.raises(kick._KickCancelError):
            kick._resolve_vod_id("https://kick.com/ch/videos/abc", cancel_check=cancel)

    def test_build_hls_formats_propagates_cancel(self, monkeypatch):
        def cancelled(url, timeout=15, cancel_check=None):
            raise kick._KickCancelError()

        monkeypatch.setattr(kick, "_fetch_url", cancelled)
        with pytest.raises(kick._KickCancelError):
            kick._build_hls_formats("https://example.com/x.m3u8", cancel_check=lambda: True)

    def test_patched_extract_cancels_with_download_error(self, monkeypatch):
        from yt_dlp.extractor.kick import KickVODIE
        from yt_dlp.utils import DownloadError

        orig_valid_url = KickVODIE._VALID_URL
        orig_real_extract = KickVODIE._real_extract
        orig_fetch_vod = kick.fetch_vod_data

        try:
            kick.patch_ytdlp_extractor()

            def cancelled(url, cancel_check=None):
                raise kick._KickCancelError()

            monkeypatch.setattr(kick, "fetch_vod_data", cancelled)

            class FakeSelf:
                def _match_id(self, url):
                    return "abcd"

                def _call_api(self, *a, **k):
                    raise RuntimeError("api dead")

                _downloader = SimpleNamespace(params={"_cancel_check": lambda: True})

            with pytest.raises(DownloadError) as ei:
                KickVODIE._real_extract(FakeSelf(), "https://kick.com/ch/videos/abcd")
            assert "zrušeno" in str(ei.value).lower()
        finally:
            KickVODIE._VALID_URL = orig_valid_url
            KickVODIE._real_extract = orig_real_extract
            kick.fetch_vod_data = orig_fetch_vod
