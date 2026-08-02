import pytest

import stahovac.platforms as platforms
from stahovac.platforms import base, kick, platform_opts, twitch, youtube


class TestDispatch:
    def test_youtube_variants(self):
        for url in (
            "https://www.youtube.com/watch?v=abc",
            "https://youtu.be/abc",
            "https://m.youtube.com/watch?v=abc",
        ):
            assert platform_opts(url) == {
                "extractor_args": {"youtube": {"player_client": ["android", "web_embedded", "android_vr"]}}
            }

    def test_kick(self):
        opts = platform_opts("https://www.kick.com/foo/videos/bar")
        assert opts == {"referer": "https://kick.com/"}

    def test_twitch(self):
        opts = platform_opts("https://www.twitch.tv/videos/123")
        assert opts["referer"] == "https://www.twitch.tv/"
        assert opts["http_headers"]["X-Device-Id"]
        assert opts["http_headers"]["User-Agent"]

    def test_unknown_host(self):
        assert platform_opts("https://vimeo.com/123") == {}

    def test_no_leakage_between_platforms(self):
        kick_opts = platform_opts("https://kick.com/x/videos/y")
        twitch_opts = platform_opts("https://www.twitch.tv/videos/1")
        youtube_opts = platform_opts("https://www.youtube.com/watch?v=abc")

        assert "http_headers" not in kick_opts
        assert "X-Device-Id" not in kick_opts
        assert "extractor_args" not in kick_opts

        assert "referer" in twitch_opts
        assert "extractor_args" not in twitch_opts

        assert "referer" not in youtube_opts
        assert "http_headers" not in youtube_opts


class TestModuleContract:
    def test_every_platform_has_hosts_and_build_opts(self):
        for module in platforms.PLATFORMS:
            assert getattr(module, "hosts", None)
            assert callable(getattr(module, "build_opts", None))

    def test_hosts_distinct(self):
        all_hosts = []
        for module in platforms.PLATFORMS:
            all_hosts.extend(module.hosts)
        assert len(all_hosts) == len(set(all_hosts))


class TestBase:
    def test_base_opts_is_shared_and_empty(self):
        assert base.base_opts("https://anywhere.example.com") == {}

    def test_base_opts_merged_by_dispatcher(self):
        original = base.base_opts

        def fake_base(url):
            return {"socket_timeout": 5}

        try:
            base.base_opts = fake_base
            opts = platform_opts("https://www.twitch.tv/videos/1")
            assert opts["socket_timeout"] == 5
        finally:
            base.base_opts = original


class TestPatchExtractors:
    def test_calls_kick_patch(self, monkeypatch):
        called = []

        def fake_patch():
            called.append("kick")

        monkeypatch.setattr(kick, "patch_ytdlp_extractor", fake_patch)
        platforms.patch_platform_extractors()
        assert called == ["kick"]

    def test_platforms_without_patch_are_skipped(self):
        assert getattr(youtube, "patch_ytdlp_extractor", None) is None
        assert getattr(twitch, "patch_ytdlp_extractor", None) is None
        assert hasattr(kick, "patch_ytdlp_extractor")


def test_utils_urls_alias_removed():
    import sys

    assert "stahovac.utils.urls" not in sys.modules


@pytest.mark.parametrize(
    "url,module",
    [
        ("https://kick.com/a/videos/b", kick),
        ("https://www.twitch.tv/videos/1", twitch),
        ("https://www.youtube.com/watch?v=1", youtube),
        ("https://youtu.be/1", youtube),
    ],
)
def test_platform_for(url, module):
    assert platforms._platform_for(url) is module
