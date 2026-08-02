"""Auditové testy pro nekryté větve (metadata, validator, models, ssl, cookies)."""

from stahovac.core.metadata import MetadataService
from stahovac.core.validator import validate_crf, validate_time_range
from stahovac.models import DownloadParams, VideoMetadata
from stahovac.utils.cookies import resolve_cookies_opts, validate_cookies_file
from stahovac.utils.ssl import _cafile, make_ssl_context


def _make_meta(title):
    return VideoMetadata(title=title, uploader="u", duration=0, thumbnail="", description="")


class _FakeYDL:
    def __init__(self, opts=None):
        self.opts = opts or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        return {
            "title": "T",
            "uploader": "U",
            "duration": 60,
            "formats": [{"height": 1080}, {"height": 720}],
        }


class TestMetadataFetch:
    def test_fetch_returns_cached(self, monkeypatch):
        svc = MetadataService()
        meta = _make_meta("Cached")
        svc._add_to_cache("https://example.com/v", meta)
        calls = {"n": 0}
        monkeypatch.setattr(svc, "fetch_info", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or {})
        assert svc.fetch("https://example.com/v", {}) is meta
        assert calls["n"] == 0

    def test_fetch_sync_waits_for_slow_worker(self, monkeypatch):
        import time

        from stahovac.core import metadata as metadata_mod

        class FakeYDL(_FakeYDL):
            def extract_info(self, url, download=False):
                time.sleep(0.2)
                return {"title": "T", "uploader": "U", "duration": 5, "formats": []}

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", FakeYDL)
        svc = MetadataService()
        result = svc.fetch_sync("https://example.com/v", {})
        assert result is not None
        assert result.title == "T"

    def test_fetch_sync_error_reports_and_returns_none(self, monkeypatch):
        logs = []
        svc = MetadataService(log_callback=lambda text: logs.append(text))

        def boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(svc, "fetch", boom)
        assert svc.fetch_sync("https://example.com/v", {}) is None
        assert any("Nemohu načíst metadata" in line for line in logs)

    def test_extract_impl_applies_extra_opts(self, monkeypatch):
        from stahovac.core import metadata as metadata_mod

        captured = {}

        class FakeYDL(_FakeYDL):
            def __init__(self, opts):
                captured["opts"] = opts

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", FakeYDL)
        svc = MetadataService()
        svc._extract_impl("https://example.com/v", {}, extra_opts={"test_flag": 1})
        assert captured["opts"]["test_flag"] == 1

    def test_store_info_evicts_oldest(self, monkeypatch):
        from stahovac.core import metadata as metadata_mod

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", _FakeYDL)
        svc = MetadataService(cache_max=1)
        svc.fetch_info("https://example.com/1", {})
        svc.fetch_info("https://example.com/2", {})
        assert svc.get_cached("https://example.com/1") is None
        assert svc.get_cached("https://example.com/2") is not None


class TestValidateCrf:
    def test_valid(self):
        assert validate_crf("23") is None

    def test_non_numeric(self):
        assert validate_crf("abc") is not None

    def test_out_of_range(self):
        assert validate_crf("100") is not None
        assert validate_crf("-1") is not None

    def test_none(self):
        assert validate_crf(None) is not None


class TestValidateTimeRange:
    def test_end_option_to_end_skips_end_check(self):
        assert validate_time_range("00:00", "garbage", "Do konce videa") is None

    def test_end_before_start(self):
        assert validate_time_range("00:10:00", "00:05:00", "Manuální čas") is not None

    def test_invalid_start_format(self):
        assert validate_time_range("abc", "00:05:00", "Manuální čas") is not None


class TestDownloadParamsCoercion:
    def test_from_dict_invalid_int_defaults(self):
        params = DownloadParams.from_dict({"crf": "abc", "re_encode": True})
        assert params.crf == 23

    def test_from_dict_none_crf_defaults(self):
        params = DownloadParams.from_dict({"crf": None})
        assert params.crf == 23


class TestSsl:
    def _clear_caches(self):
        _cafile.cache_clear()
        make_ssl_context.cache_clear()

    def test_cafile_none_without_certifi(self, monkeypatch):
        import stahovac.utils.ssl as ssl_mod

        self._clear_caches()
        monkeypatch.setattr(ssl_mod, "certifi", None)
        assert ssl_mod._cafile() is None
        ctx = ssl_mod.make_ssl_context()
        assert ctx is not None
        self._clear_caches()


class TestCookies:
    def test_validate_cookies_file_oserror(self, monkeypatch, tmp_path):
        import stahovac.utils.cookies as cookies_mod

        p = tmp_path / "cookies.txt"
        p.write_text("x")

        def fake_open(*a, **k):
            raise OSError("denied")

        monkeypatch.setattr(cookies_mod, "open", fake_open, raising=False)
        assert validate_cookies_file(str(p)) == "soubor nelze otevřít."

    def test_resolve_cookies_youtube_ignored(self):
        config = {"cookies_source": "Chrome", "cookies_file_path": ""}
        assert resolve_cookies_opts(config, "https://youtube.com/watch?v=x") == {}

    def test_validate_cookies_file_missing(self, tmp_path):
        assert validate_cookies_file(str(tmp_path / "missing.txt")) == "soubor neexistuje."
