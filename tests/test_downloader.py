import sys
import threading
import time
from pathlib import Path

import pytest
import yt_dlp

import stahovac.core.downloader as dl_mod
from stahovac.config.constants import QUALITY_BEST, MediaFormat
from stahovac.core.downloader import (
    JOBS_DIR_NAME,
    Downloader,
    _build_ffmpeg_cmd,
    _build_ranged_cmd,
    _build_ydl_opts,
    _can_ranged_hls,
    _ensure_ffmpeg_ready,
    _estimate_cut_duration,
    _ffmpeg_timeout,
    _find_job_file,
    _ranged_output_name,
    _sanitize_cmd,
    _select_hls_formats,
)
from stahovac.core.metadata import MetadataService, pick_subtitle_langs
from stahovac.models import DownloadParams, DownloadState
from stahovac.platforms import platform_opts


def _params(**overrides):
    params = DownloadParams(
        url="https://www.youtube.com/watch?v=abc",
        quality=QUALITY_BEST,
        format_choice="Video + audio (MP4)",
        output_folder="/tmp/out",
    )
    return params if not overrides else DownloadParams.from_dict({**params.to_dict(), **overrides})


class TestFindJobFile:
    def test_finds_first_file(self, tmp_path):
        (tmp_path / "Some [deadbeef].mp4").write_text("x")
        (tmp_path / "Other [aaa].mp4").write_text("x")
        result = _find_job_file(tmp_path)
        assert result is not None
        assert result.name in {"Some [deadbeef].mp4", "Other [aaa].mp4"}

    def test_no_match_returns_none(self, tmp_path):
        assert _find_job_file(tmp_path) is None


class TestSanitizeCmd:
    def test_masks_url_query_string(self):
        cmd = ["ffmpeg", "-i", "https://x/playlist.m3u8?token=secret&expires=123", "-c", "copy", "out.mp4"]
        out = _sanitize_cmd(cmd)
        assert "secret" not in out
        assert "expires" not in out
        assert "playlist.m3u8" in out
        assert "token" not in out

    def test_masks_cookie_and_auth_headers(self):
        headers = "Referer: https://x/\r\nCookie: sid=SECRET; other=1\r\nAuthorization: Bearer TOK"
        out = _sanitize_cmd(["ffmpeg", "-headers", headers, "-i", "https://x/stream.m3u8", "out.mp4"])
        assert "SECRET" not in out
        assert "other=1" not in out
        assert "TOK" not in out
        assert "Cookie" in out
        assert "Authorization" in out

    def test_local_cut_cmd_unchanged(self):
        cmd = ["ffmpeg", "-y", "-ss", "00:00:01", "-i", "/tmp/in.mp4", "-c", "copy", "/tmp/out.mp4"]
        assert _sanitize_cmd(cmd) == " ".join(cmd)


class TestEnsureFfmpegReady:
    def test_waits_when_trim_needed(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dl_mod, "wait_until_ready", lambda: calls.append("wait"))
        _ensure_ffmpeg_ready()
        assert calls == ["wait"]

    def test_waits_when_mp3(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dl_mod, "wait_until_ready", lambda: calls.append("wait"))
        _ensure_ffmpeg_ready()
        assert calls == ["wait"]

    def test_waits_for_whole_video_mp4(self, monkeypatch):
        """Merge video+audio (bestvideo+bestaudio) vyžaduje FFmpeg i bez ořezu."""
        calls = []
        monkeypatch.setattr(dl_mod, "wait_until_ready", lambda: calls.append("wait"))
        _ensure_ffmpeg_ready()
        assert calls == ["wait"]


class TestWorkerFfmpegOrdering:
    def test_opts_built_after_ffmpeg_becomes_ready(self, monkeypatch, tmp_path):
        """Regrese: `_build_ydl_opts` se musí volat AŽ PO čekání na FFmpeg.

        Když se FFmpeg stahuje na pozadí (auto-install), musí `ffmpeg_location`
        ukazovat na čerstvě nainstalovanou binárku. Kdyby se opts stavěly před
        čekáním, yt-dlp by FFmpeg nenašel (chyba "ffmpeg is not installed").
        """
        state = {"ready": False}

        def fake_find():
            return Path("/opt/ffmpeg/bin/ffmpeg") if state["ready"] else None

        monkeypatch.setattr(dl_mod, "find_ffmpeg", fake_find)
        monkeypatch.setattr(dl_mod, "wait_until_ready", lambda: state.__setitem__("ready", True))

        captured = {}

        def fake_build_opts(params, config, hook, subtitle_langs=None):
            captured["found"] = fake_find() is not None
            return {
                "_job_id": "j1",
                "_job_dir": str(tmp_path / ".jobs" / "j1"),
                "outtmpl": str(tmp_path / "x.%(ext)s"),
            }

        monkeypatch.setattr(dl_mod, "_build_ydl_opts", fake_build_opts)

        dl = Downloader({})
        dl._get_title = lambda url: "T"
        dl._download_with_ytdlp = lambda url, opts, job_id: True
        dl._download_worker(_params(whole_video=True, output_folder=str(tmp_path)), "j1")
        assert captured["found"] is True


class TestBuildYdlOpts:
    def test_mp4_default(self):
        opts = _build_ydl_opts(_params(), {}, lambda d: None)
        assert opts["format"] == "bestvideo+bestaudio/best"
        assert opts["merge_output_format"] == "mp4"
        assert "format_sort" not in opts
        assert opts["outtmpl"].endswith("%(title)s.%(ext)s")

    def test_mp3(self):
        opts = _build_ydl_opts(_params(format_choice=MediaFormat.MP3.value), {}, lambda d: None)
        assert opts["format"] == "bestaudio/best"
        assert opts["format_sort"] == ["res:0", "vcodec", "br"]
        assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"
        assert opts["postprocessors"][0]["preferredcodec"] == "mp3"

    def test_subs(self):
        opts = _build_ydl_opts(_params(format_choice=MediaFormat.SUBS.value), {}, lambda d: None)
        assert opts["writesubtitles"] is True
        assert opts["writeautomaticsub"] is True
        assert opts["skip_download"] is True
        assert opts["postprocessors"][0]["key"] == "FFmpegSubtitlesConvertor"

    def test_quality_sort(self):
        opts = _build_ydl_opts(_params(quality="1080p"), {}, lambda d: None)
        assert opts["format_sort"] == ["res:1080", "codec:av1:mpeg4"]

    def test_outtmpl_quality_suffix(self):
        opts = _build_ydl_opts(_params(quality="720p"), {}, lambda d: None)
        assert opts["outtmpl"].endswith(" [720p].%(ext)s")

    def test_cookies_in_opts(self):
        config = {"cookies_source": "Chrome", "cookies_file_path": ""}
        opts = _build_ydl_opts(_params(url="https://kick.com/ch/videos/abc"), config, lambda d: None)
        assert opts["cookiesfrombrowser"] == ("chrome",)

    def test_ffmpeg_location_when_found(self, monkeypatch):
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: Path("/opt/ffmpeg/bin/ffmpeg"))
        opts = _build_ydl_opts(_params(), {}, lambda d: None)
        assert opts["ffmpeg_location"] == str(Path("/opt/ffmpeg/bin"))

    def test_ffmpeg_location_absent_when_missing(self, monkeypatch):
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: None)
        opts = _build_ydl_opts(_params(), {}, lambda d: None)
        assert "ffmpeg_location" not in opts

    def test_subs_sets_subtitleslangs_when_provided(self):
        opts = _build_ydl_opts(
            _params(format_choice=MediaFormat.SUBS.value),
            {},
            lambda d: None,
            subtitle_langs=["cs", "en"],
        )
        assert opts["subtitleslangs"] == ["cs", "en"]

    def test_subs_omits_subtitleslangs_when_missing(self):
        opts = _build_ydl_opts(_params(format_choice=MediaFormat.SUBS.value), {}, lambda d: None)
        assert "subtitleslangs" not in opts


class TestPickSubtitleLangs:
    def test_prefers_original_language_with_en_fallback(self):
        info = {
            "language": "cs",
            "automatic_captions": {"cs": [], "cs-orig": [], "en": [], "de": []},
            "subtitles": {},
        }
        assert pick_subtitle_langs(info) == ["cs", "en"]

    def test_uses_orig_suffix_when_language_field_missing(self):
        info = {
            "language": None,
            "automatic_captions": {"ko": [], "ko-orig": [], "en": []},
            "subtitles": {},
        }
        assert pick_subtitle_langs(info) == ["ko", "en"]

    def test_includes_manual_subtitle_languages(self):
        info = {
            "language": "cs",
            "automatic_captions": {"cs": [], "cs-orig": [], "en": []},
            "subtitles": {"cs": [], "en": [], "de": []},
        }
        assert pick_subtitle_langs(info) == ["cs", "en", "de"]

    def test_no_en_when_not_available(self):
        info = {
            "language": None,
            "automatic_captions": {},
            "subtitles": {"cs": []},
        }
        assert pick_subtitle_langs(info) == ["cs"]

    def test_dedupes_original_manual_and_orig_suffix(self):
        info = {
            "language": "cs",
            "automatic_captions": {"cs": [], "cs-orig": [], "en": []},
            "subtitles": {"cs": []},
        }
        assert pick_subtitle_langs(info) == ["cs", "en"]

    def test_returns_none_for_empty_or_missing_info(self):
        assert pick_subtitle_langs(None) is None
        assert pick_subtitle_langs({}) is None


class TestAudioFormatSelection:
    KICK_VIDEO_ONLY = [
        {
            "format_id": "hls-1080",
            "url": "https://x/1080.m3u8",
            "ext": "mp4",
            "height": 1080,
            "vcodec": "avc1",
            "acodec": "none",
            "protocol": "m3u8_native",
        },
        {
            "format_id": "hls-720",
            "url": "https://x/720.m3u8",
            "ext": "mp4",
            "height": 720,
            "vcodec": "avc1",
            "acodec": "none",
            "protocol": "m3u8_native",
        },
        {
            "format_id": "hls-360",
            "url": "https://x/360.m3u8",
            "ext": "mp4",
            "height": 360,
            "vcodec": "avc1",
            "acodec": "none",
            "protocol": "m3u8_native",
        },
    ]
    KICK_WITH_AUDIO = [
        {
            "format_id": "hls-1080",
            "url": "https://x/1080.m3u8",
            "ext": "mp4",
            "height": 1080,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "protocol": "m3u8_native",
        },
        {
            "format_id": "hls-128k",
            "url": "https://x/128k.m3u8",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
            "protocol": "m3u8_native",
        },
    ]
    YT_WITH_AUDIO = [
        {
            "format_id": "299",
            "url": "https://x/299.mp4",
            "ext": "mp4",
            "height": 1080,
            "vcodec": "avc1",
            "acodec": "none",
        },
        {"format_id": "140", "url": "https://x/140.m4a", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "abr": 128},
        {
            "format_id": "251",
            "url": "https://x/251.webm",
            "ext": "webm",
            "vcodec": "none",
            "acodec": "opus",
            "abr": 160,
        },
    ]

    def _select(self, formats):
        opts = _build_ydl_opts(_params(format_choice=MediaFormat.MP3.value), {}, lambda d: None)
        info = {"id": "1", "title": "t", "ext": "mp4", "extractor": "generic", "formats": formats}
        ydl = yt_dlp.YoutubeDL(opts)
        result = ydl.process_ie_result(info, download=False)
        requested = result.get("requested_formats")
        if requested:
            return [f["format_id"] for f in requested]
        return result.get("format_id")

    def test_kick_video_only_picks_lowest_not_best(self):
        assert self._select(self.KICK_VIDEO_ONLY) == "hls-360"

    def test_kick_with_audio_only_picks_audio(self):
        assert self._select(self.KICK_WITH_AUDIO) == "hls-128k"

    def test_youtube_audio_only_picks_best_audio(self):
        assert self._select(self.YT_WITH_AUDIO) == "251"


class TestPlatformOpts:
    def test_kick(self):
        assert platform_opts("https://kick.com/foo/videos/bar") == {"referer": "https://kick.com/"}

    def test_twitch(self):
        opts = platform_opts("https://www.twitch.tv/videos/123")
        assert opts["referer"] == "https://www.twitch.tv/"
        assert "User-Agent" in opts["http_headers"]
        assert "X-Device-Id" in opts["http_headers"]

    def test_youtube(self):
        assert platform_opts("https://www.youtube.com/watch?v=abc") == {
            "extractor_args": {"youtube": {"player_client": ["android", "web_embedded", "android_vr"]}}
        }

    def test_unknown(self):
        assert platform_opts("https://vimeo.com/123") == {}


class TestMetadataService:
    def test_get_cached(self):
        svc = MetadataService()
        assert svc.get_cached("https://example.com") is None

    def test_add_to_cache(self):
        svc = MetadataService(cache_max=2)
        meta = _make_meta("A")
        svc._add_to_cache("a", meta)
        assert svc.get_cached("a") is meta

    def test_cache_eviction(self):
        svc = MetadataService(cache_max=2)
        m1 = _make_meta("1")
        m2 = _make_meta("2")
        m3 = _make_meta("3")
        svc._add_to_cache("1", m1)
        svc._add_to_cache("2", m2)
        svc._add_to_cache("3", m3)
        assert svc.get_cached("1") is None
        assert svc.get_cached("2") is m2
        assert svc.get_cached("3") is m3

    def test_fetch_sync_returns_cached(self, monkeypatch):
        svc = MetadataService()
        svc._add_to_cache("https://example.com", _make_meta("Cached"))
        monkeypatch.setattr("stahovac.core.metadata.yt_dlp", None)
        result = svc.fetch_sync("https://example.com", {})
        assert result is not None
        assert result.title == "Cached"

    def test_fetch_sync_cancelled(self, monkeypatch):
        svc = MetadataService()
        assert svc.fetch_sync("https://example.com", {}, cancel_check=lambda: True) is None

    def test_fetch_sync_with_mocked_ydl(self, monkeypatch):
        from stahovac.core import metadata as metadata_mod

        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                return {
                    "title": "Mock Title",
                    "uploader": "Mock Uploader",
                    "duration": 120,
                    "formats": [{"height": 1080}, {"height": 720}, {"height": "720"}],
                }

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", FakeYDL)
        svc = MetadataService()
        result = svc.fetch_sync("https://example.com", {})
        assert result is not None
        assert result.title == "Mock Title"
        assert result.duration == 120
        assert result.available_resolutions == [1080, 720]
        assert svc.get_cached("https://example.com") is result

    def test_fetch_sync_propagates_cancel_check_to_opts(self, monkeypatch):
        from stahovac.core import metadata as metadata_mod

        captured = {}

        class FakeYDL:
            def __init__(self, opts):
                captured["opts"] = opts

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                return {"title": "T", "uploader": "U", "duration": 1, "formats": []}

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", FakeYDL)
        svc = MetadataService()
        cancelled = {"flag": False}
        svc.fetch_sync("https://example.com", {}, cancel_check=lambda: cancelled["flag"])
        assert captured["opts"]["_cancel_check"]() is False
        cancelled["flag"] = True
        assert captured["opts"]["_cancel_check"]() is True

    def test_fetch_info_returns_raw_formats(self, monkeypatch):
        from stahovac.core import metadata as metadata_mod

        class FakeYDL:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                return {
                    "title": "T",
                    "uploader": "U",
                    "duration": 60,
                    "formats": [
                        {"height": 1080, "protocol": "m3u8_native", "url": "https://x/v.m3u8"},
                        {"height": 720, "protocol": "m3u8_native", "url": "https://x/v720.m3u8"},
                    ],
                }

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", FakeYDL)
        svc = MetadataService()
        info = svc.fetch_info("https://example.com", {})
        assert info is not None
        assert len(info["formats"]) == 2
        assert svc.get_cached("https://example.com") is not None
        assert svc.get_cached("https://example.com").available_resolutions == [1080, 720]

    def test_fetch_info_uses_cache(self, monkeypatch):
        from stahovac.core import metadata as metadata_mod

        calls = {"n": 0}

        class FakeYDL:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                calls["n"] += 1
                return {"title": "T", "uploader": "U", "duration": 1, "formats": []}

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", FakeYDL)
        svc = MetadataService()
        svc.fetch_info("https://example.com", {})
        svc.fetch_info("https://example.com", {})
        assert calls["n"] == 1

    def test_extract_impl_wraps_ytdlp_errors_into_metadata_error(self, monkeypatch):
        from stahovac.core import metadata as metadata_mod
        from stahovac.core.metadata import MetadataError

        class FakeYDL:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                raise yt_dlp.utils.DownloadError("HTTP Error 404")

        monkeypatch.setattr(metadata_mod.yt_dlp, "YoutubeDL", FakeYDL)
        svc = MetadataService()
        with pytest.raises(MetadataError) as excinfo:
            svc.fetch_info("https://example.com", {})
        assert "404" in str(excinfo.value)


def _make_meta(title):
    from stahovac.models import VideoMetadata

    return VideoMetadata(
        title=title,
        uploader="u",
        duration=0,
        thumbnail="",
        description="",
    )


class TestProgressHook:
    def test_downloading_status(self):
        dl = Downloader({})
        calls = []

        dl.on_progress = lambda job_id, percent, speed, eta: calls.append((job_id, percent, speed, eta))
        dl._progress_hook(
            "j1",
            {
                "status": "downloading",
                "total_bytes": 200,
                "downloaded_bytes": 50,
                "speed": 1_500,
                "eta": 30,
            },
        )
        assert calls == [("j1", 25.0, "2 kB/s", "30s")]

    def test_finished_status(self):
        dl = Downloader({})
        statuses = []

        dl.on_status = lambda job_id, text, color: statuses.append((job_id, text, color))
        dl._progress_hook("j1", {"status": "finished"})
        assert statuses[0][0] == "j1"
        assert statuses[0][1] == "Dokončeno, zpracovávám…"

    def test_cancel_raises(self):
        dl = Downloader({})
        dl.cancel()
        with pytest.raises(yt_dlp.utils.DownloadCancelled):
            dl._progress_hook("j1", {"status": "downloading"})


class TestCutWithFfmpeg:
    def test_no_ffmpeg_returns_none(self, monkeypatch):
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: None)
        dl = Downloader({})
        logs = []
        dl.on_log = lambda text: logs.append(text)
        result = dl._cut_with_ffmpeg(Path("/tmp/in.mp4"), "00:00", "00:00", "Do konce videa")
        assert result is None
        assert any("FFmpeg není nainstalován" in line for line in logs)

    def test_uses_found_ffmpeg_path(self, monkeypatch, tmp_path):
        fake_bin = Path("/opt/ffmpeg/bin/ffmpeg")
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: fake_bin)
        input_path = tmp_path / "in.mp4"
        input_path.write_text("x")
        output_path = tmp_path / "in [00h00m00s - 00h00m05s].mp4"
        output_path.write_text("x")
        dl = Downloader({})
        logs = []
        dl.on_log = lambda text: logs.append(text)
        dl.on_progress = lambda *a, **k: None
        dl._run_ffmpeg = lambda *a, **k: True
        monkeypatch.setattr(dl_mod.subprocess, "Popen", lambda *a, **k: object())
        result = dl._cut_with_ffmpeg(input_path, "00:00", "00:05", "Do určitého času")
        assert result == output_path
        assert any(str(fake_bin) in line for line in logs)


class TestBuildFfmpegCmd:
    def test_reencode_precise_seek(self, tmp_path):
        cmd, out = _build_ffmpeg_cmd(
            tmp_path / "in.mp4", "00:01:00", "00:02:00", "Do určitého času", re_encode=True, crf=20, preset="slow"
        )
        assert cmd[:3] == ["ffmpeg", "-y", "-i"]
        assert "-ss" in cmd
        assert cmd.index("-ss") > cmd.index("-i")
        assert "-c:v" in cmd and "libx264" in cmd
        assert "-preset" in cmd and "slow" in cmd
        assert "-crf" in cmd and "20" in cmd
        assert "-to" in cmd and "00:02:00" in cmd
        assert "copy" not in cmd
        assert "in [00h01m00s - 00h02m00s].mp4" in out.name

    def test_copy_fast_seek(self, tmp_path):
        cmd, out = _build_ffmpeg_cmd(tmp_path / "in.mp4", "00:01:00", "00:02:00", "Do určitého času")
        assert "-ss" in cmd
        assert cmd.index("-ss") < cmd.index("-i")
        assert "-c" in cmd and "copy" in cmd
        assert "-avoid_negative_ts" in cmd
        assert "-c:v" not in cmd

    def test_to_end_of_video(self, tmp_path):
        cmd, out = _build_ffmpeg_cmd(tmp_path / "in.mp4", "00:01:00", "00:02:00", "Do konce videa")
        assert "-to" not in cmd
        assert " [00h01m00s-inf]" in out.name

    def test_movflags_faststart(self, tmp_path):
        cmd, _ = _build_ffmpeg_cmd(tmp_path / "in.mp4", "00:00:00", "00:00:05", "Do určitého času")
        assert cmd[-3:] == ["-movflags", "+faststart", str(tmp_path / "in [00h00m00s - 00h00m05s].mp4")]

    def test_custom_ffmpeg_bin(self, tmp_path):
        cmd, _ = _build_ffmpeg_cmd(
            tmp_path / "in.mp4", "00:00", "00:00", "Do konce videa", ffmpeg_bin="/opt/bin/ffmpeg"
        )
        assert cmd[0] == "/opt/bin/ffmpeg"

    def test_very_long_input_stem_capped(self, tmp_path):
        cmd, out = _build_ffmpeg_cmd(tmp_path / ("L" * 300 + ".mp4"), "00:01:00", "00:02:00", "Do určitého času")
        assert len(out.name) <= 255
        assert out.name.endswith(".mp4")
        assert out.name.startswith("L" * 150)


class TestEstimateCutDuration:
    def test_to_end_of_video_unknown(self):
        assert _estimate_cut_duration("00:00", "00:00", "Do konce videa") is None

    def test_with_end_time(self):
        assert _estimate_cut_duration("00:01:00", "00:03:30", "Do určitého času") == 150

    def test_none_end_option_means_no_cut(self):
        assert _estimate_cut_duration("00:00", "00:00", None) is None


class TestFfmpegTimeout:
    def test_reencode_longer_than_copy(self):
        assert _ffmpeg_timeout(60, True) > _ffmpeg_timeout(60, False)

    def test_unknown_length_uses_generous_default(self):
        assert _ffmpeg_timeout(None, False) == 7200.0

    def test_short_segment_minimum(self):
        assert _ffmpeg_timeout(1, False) >= 60.0


class TestRunFfmpeg:
    @staticmethod
    def _fake_proc(lines=None):
        lines = lines or []

        class FakeStdErr:
            def __init__(self, src):
                self._src = list(src)

            def readline(self):
                if not self._src:
                    return ""
                return self._src.pop(0)

        class FakeProc:
            def __init__(self):
                self.stderr = FakeStdErr(lines)
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

        return FakeProc()

    def test_cancel_kills_and_returns_false(self, monkeypatch):
        dl = Downloader({})
        dl.cancel()
        proc = self._fake_proc()
        killed = []
        monkeypatch.setattr(dl_mod, "_kill_process", lambda p: killed.append(p))
        assert dl._run_ffmpeg(proc, None, False, "j1") is False
        assert killed == [proc]

    def test_success_returns_true(self):
        dl = Downloader({})
        assert dl._run_ffmpeg(self._fake_proc(), None, False, "j1") is True

    def test_failure_returncode_false(self):
        proc = self._fake_proc()
        proc.returncode = 1
        dl = Downloader({})
        assert dl._run_ffmpeg(proc, None, False, "j1") is False

    def test_progress_reported(self):
        dl = Downloader({})
        progresses = []
        dl.on_progress = lambda job_id, percent, speed, eta: progresses.append((job_id, percent))
        lines = ["ffmpeg version 6", "time=00:00:05.50 bitrate=123kbits/s", "time=00:00:10.00 bitrate=100kbits/s"]
        assert dl._run_ffmpeg(self._fake_proc(lines), 100, False, "j1") is True
        assert ("j1", 5.0) in progresses
        assert ("j1", 10.0) in progresses

    def test_cancel_mid_run_kills(self, monkeypatch):
        release = threading.Event()

        class BlockingStdErr:
            def readline(self):
                release.wait(timeout=3)
                return b""

        class BlockingProc:
            stderr = BlockingStdErr()
            returncode = 0

            def wait(self, timeout=None):
                return 0

        proc = BlockingProc()
        killed = []
        monkeypatch.setattr(dl_mod, "_kill_process", lambda p: (killed.append(p), release.set()))

        dl = Downloader({})
        results = []
        t = threading.Thread(target=lambda: results.append(dl._run_ffmpeg(proc, None, False, "j1")))
        t.start()
        time.sleep(0.2)
        dl.cancel()
        t.join(timeout=3)

        assert results == [False]
        assert killed == [proc]


class TestMoveOutputFiles:
    def test_moves_all_and_returns_largest(self, tmp_path):
        dl = Downloader({})
        job_dir = tmp_path / ".jobs" / "abc"
        job_dir.mkdir(parents=True)
        (job_dir / "small.mp4").write_text("x")
        (job_dir / "big.mp4").write_bytes(b"y" * 1000)
        out = tmp_path / "out"
        result = dl._move_output_files(job_dir, str(out))
        assert result == str(out / "big.mp4")
        assert (out / "big.mp4").exists()
        assert (out / "small.mp4").exists()
        assert not list(job_dir.iterdir())

    def test_empty_job_dir_returns_none(self, tmp_path):
        dl = Downloader({})
        job_dir = tmp_path / ".jobs" / "abc"
        job_dir.mkdir(parents=True)
        assert dl._move_output_files(job_dir, str(tmp_path / "out")) is None

    def test_does_not_overwrite_existing_destination(self, tmp_path):
        dl = Downloader({})
        job_dir = tmp_path / ".jobs" / "abc"
        job_dir.mkdir(parents=True)
        out = tmp_path / "out"
        out.mkdir()
        (job_dir / "video.mp4").write_bytes(b"new")
        (out / "video.mp4").write_bytes(b"old")
        result = dl._move_output_files(job_dir, str(out))
        assert (out / "video.mp4").read_bytes() == b"old"
        assert (out / "video (1).mp4").read_bytes() == b"new"
        assert result == str(out / "video (1).mp4")
        assert not list(job_dir.iterdir())


class TestUniqueDest:
    def test_returns_same_when_free(self, tmp_path):
        assert dl_mod._unique_dest(tmp_path, "a.mp4") == tmp_path / "a.mp4"

    def test_adds_counter_when_exists(self, tmp_path):
        (tmp_path / "a.mp4").write_text("x")
        assert dl_mod._unique_dest(tmp_path, "a.mp4") == tmp_path / "a (1).mp4"
        (tmp_path / "a (1).mp4").write_text("x")
        assert dl_mod._unique_dest(tmp_path, "a.mp4") == tmp_path / "a (2).mp4"

    def test_counter_respects_suffix(self, tmp_path):
        (tmp_path / "a.mkv").write_text("x")
        assert dl_mod._unique_dest(tmp_path, "a.mkv") == tmp_path / "a (1).mkv"

    def test_more_than_1000_collisions_finds_free_name(self, tmp_path):
        (tmp_path / "a.mp4").write_text("x")
        for i in range(1, 1001):
            (tmp_path / f"a ({i}).mp4").write_text("x")
        assert dl_mod._unique_dest(tmp_path, "a.mp4") == tmp_path / "a (1001).mp4"


class TestFinishCallbacks:
    def test_finish_success(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        results = []
        dl.on_finish = lambda job_id, success, message: results.append((job_id, success, message))
        dl._finish_success("j1", "Title", "https://example.com/video", "/tmp/x.mp4")
        assert results == [("j1", True, "Úspěch")]

    def test_finish_success_no_file(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        results = []
        dl.on_finish = lambda job_id, success, message: results.append((job_id, success, message))
        dl._finish_success("j1", "Title", "https://example.com/video", None)
        assert results == [("j1", True, "Úspěch")]

    def test_finish_fail(self):
        dl = Downloader({})
        results = []
        dl.on_finish = lambda job_id, success, message: results.append((job_id, success, message))
        dl._finish_fail("j1")
        assert results == [("j1", False, "Stahování selhalo")]

    def test_finish_once_guards_duplicates(self):
        dl = Downloader({})
        results = []
        dl.on_finish = lambda jid, s, m: results.append((jid, s, m))
        dl._finish_once("j1", True, "Úspěch")
        dl._finish_once("j1", False, "Worker finished")
        assert results == [("j1", True, "Úspěch")]

    def test_finally_fallback_sets_status_if_not_finished(self):
        dl = Downloader({})
        statuses, finishes = [], []
        dl.on_status = lambda jid, t, c: statuses.append(t)
        dl.on_finish = lambda jid, s, m: finishes.append((s, m))
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: False
        dl._finish_fail = lambda job_id: None
        dl._download_worker(_params(), "j1")
        assert finishes == [(False, "Worker finished")]
        assert any("Operace se nezdařila" in s for s in statuses)

    def test_finally_fallback_does_not_override_cancel_status(self):
        dl = Downloader({})
        statuses, finishes = [], []
        dl.on_status = lambda jid, t, c: statuses.append(t)
        dl.on_finish = lambda jid, s, m: finishes.append((s, m))
        dl.cancel()
        dl._download_worker(_params(), "j1")
        assert finishes == [(False, "Zrušeno")]
        assert "Stahování zrušeno." in statuses
        assert not any("Operace se nezdařila" in s for s in statuses)


class TestDownloadWorker:
    def _hook(self, dl, statuses=None, logs=None, finishes=None):
        dl.on_status = lambda jid, t, c: statuses.append(t) if statuses is not None else None
        dl.on_log = lambda t: logs.append(t) if logs is not None else None
        dl.on_finish = lambda jid, s, m: finishes.append((s, m)) if finishes is not None else None

    def test_cancelled_before_title(self):
        dl = Downloader({})
        finishes = []
        dl.on_finish = lambda jid, s, m: finishes.append((s, m))
        dl.cancel()
        dl._download_worker(_params(), "j1")
        assert finishes == [(False, "Zrušeno")]

    def test_cancelled_after_title(self):
        dl = Downloader({})
        finishes = []
        dl.on_finish = lambda jid, s, m: finishes.append((s, m))

        def get_title(url):
            dl.cancel()
            return "Mock Title"

        dl._get_title = get_title
        dl._download_worker(_params(), "j1")
        assert finishes == [(False, "Zrušeno")]

    def test_success_no_cut(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses, finishes = [], []
        self._hook(dl, statuses=statuses, finishes=finishes)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: True
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        (job_dir / "Mock Title.mp4").write_text("x")
        dl._download_worker(_params(output_folder=str(output), whole_video=True), "j1")
        assert finishes == [(True, "Úspěch")]
        assert "Načítám info o videu…" in statuses
        assert (output / "Mock Title.mp4").exists()
        assert not job_dir.exists()

    def test_success_with_cut(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses = []
        self._hook(dl, statuses=statuses)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: True
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        source = job_dir / "Src.mp4"
        source.write_text("x")
        trimmed = job_dir / "Src [00h00m00s - 00h00m05s].mp4"

        def fake_cut(*a, **k):
            trimmed.write_text("y")
            return trimmed

        dl._cut_with_ffmpeg = fake_cut
        dl._download_worker(
            _params(
                output_folder=str(output),
                whole_video=False,
                start_time="00:00",
                end_time="00:05",
                end_option="Manuální čas",
            ),
            "j1",
        )
        assert "Ořezávám video…" in statuses
        assert (output / "Src [00h00m00s - 00h00m05s].mp4").exists()
        assert not (output / "Src.mp4").exists()
        assert not job_dir.exists()

    def test_cut_failure_keeps_source(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses = []
        self._hook(dl, statuses=statuses)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: True
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        source = job_dir / "Src.mp4"
        source.write_text("x")
        dl._cut_with_ffmpeg = lambda *a, **k: None
        dl._download_worker(
            _params(
                output_folder=str(output),
                whole_video=False,
                start_time="00:00",
                end_time="00:05",
                end_option="Manuální čas",
            ),
            "j1",
        )
        assert any("Ořez se nezdařil" in s for s in statuses)
        assert (output / "Src.mp4").exists()

    def test_download_failed(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        finishes = []
        self._hook(dl, finishes=finishes)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: False
        dl._download_worker(_params(), "j1")
        assert finishes == [(False, "Stahování selhalo")]

    def test_no_output_file_reports_failure(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses, finishes = [], []
        self._hook(dl, statuses=statuses, finishes=finishes)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: True
        dl._download_worker(_params(output_folder=str(tmp_path), whole_video=True), "j1")
        assert finishes == [(False, "Stahování selhalo")]
        assert any("nenalezen výstupní soubor" in s for s in statuses)

    def test_cancel_sets_cancelled_state_and_status(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses, finishes = [], []
        self._hook(dl, statuses=statuses, finishes=finishes)
        states = []
        dl.on_state = lambda s: states.append(s)
        dl.cancel()
        dl._download_worker(_params(), "j1")
        assert finishes == [(False, "Zrušeno")]
        assert "Stahování zrušeno." in statuses
        assert DownloadState.CANCELLED in states

    def test_failed_job_dir_removed_by_default(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        self._hook(dl)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: False
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        (job_dir / "partial.mp4").write_text("x")
        dl._download_worker(_params(output_folder=str(output)), "j1")
        assert not job_dir.exists()

    def test_failed_job_dir_kept_with_debug_env(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        monkeypatch.setenv(dl_mod.AETHER_KEEP_FAILED_JOBS, "1")
        dl = Downloader({})
        logs = []
        self._hook(dl, logs=logs)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: False
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        (job_dir / "partial.mp4").write_text("x")
        dl._download_worker(_params(output_folder=str(output)), "j1")
        assert job_dir.exists()
        assert any("pracovní adresář zachován" in line for line in logs)
        monkeypatch.delenv(dl_mod.AETHER_KEEP_FAILED_JOBS, raising=False)

    def test_large_incomplete_files_removed_on_fail(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        finishes = []
        self._hook(dl, finishes=finishes)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: False
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        (job_dir / "Huge [j1].part").write_bytes(b"x" * (2 * 1024 * 1024))
        dl._download_worker(_params(output_folder=str(output)), "j1")
        assert finishes == [(False, "Stahování selhalo")]
        assert not job_dir.exists()

    def test_exception_handled(self):
        dl = Downloader({})
        finishes, logs = [], []
        self._hook(dl, logs=logs, finishes=finishes)
        dl._get_title = lambda url: (_ for _ in ()).throw(RuntimeError("boom"))
        dl._download_worker(_params(), "j1")
        assert finishes == [(False, "Operace se nezdařila")]
        assert any("Kritická výjimka" in line for line in logs)

    def test_start_already_running(self):
        dl = Downloader({})
        finishes = []
        dl.on_finish = lambda jid, s, m: finishes.append((jid, s, m))

        class FakeThread:
            def is_alive(self):
                return True

        dl._thread = FakeThread()
        result = dl.start(_params())
        assert result is False
        assert finishes == []

    def test_start_returns_true_when_idle(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        dl._download_worker = lambda params, job_id: time.sleep(0.2)
        result = dl.start(_params())
        assert result is True
        assert dl.is_busy() is True
        dl._thread.join(timeout=5)
        assert dl.is_busy() is False

    def test_force_stop_cancels_and_cleans_children(self, monkeypatch):
        dl = Downloader({})
        cleaned = []

        def fake_cleanup():
            cleaned.append(True)

        monkeypatch.setattr(dl_mod, "_cleanup_child_processes", fake_cleanup)
        dl.force_stop()
        assert dl.is_cancelled is True
        assert cleaned == [True]

    def test_start_spawns_worker(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        finishes = []
        self._hook(dl, finishes=finishes)
        dl._get_title = lambda url: "Mock Title"

        def fake_download(url, opts, job_id):
            job_dir = Path(opts["_job_dir"])
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "Mock Title.mp4").write_text("x")
            return True

        dl._download_with_ytdlp = fake_download
        dl.start(_params(output_folder=str(tmp_path), whole_video=True))
        dl._thread.join(timeout=5)
        assert finishes == [(True, "Úspěch")]
        assert dl.is_cancelled is False

    def test_worker_passes_cancel_check_into_opts(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        captured = {}
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: captured.update(opts) or True
        dl.start(_params(output_folder=str(tmp_path), whole_video=True))
        dl._thread.join(timeout=5)
        assert captured["_cancel_check"]() is False

    def test_worker_subs_uses_video_original_language(self, tmp_path):
        """Regrese: při stahování titulků se má vyžádat jazyk videa (původní),
        ne slepě angličtina – jinak yt-dlp vybere `en` a pro neanglická videa
        stáhne nic (nebo vyhlásí chybu o `en`)."""
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        captured = {}
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: captured.update(opts) or True
        dl.metadata._store_info(
            "https://www.youtube.com/watch?v=abc",
            {
                "language": "cs",
                "automatic_captions": {"cs": [], "cs-orig": [], "en": [], "de": []},
                "subtitles": {},
            },
        )
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        (job_dir / "Mock Title.cs.srt").write_text("x")
        dl._download_worker(
            _params(format_choice=MediaFormat.SUBS.value, output_folder=str(output)),
            "j1",
        )
        assert captured["subtitleslangs"] == ["cs", "en"]
        assert captured["writesubtitles"] is True

    def test_cancel_frees_thread_for_restart(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        finishes = []
        self._hook(dl, finishes=finishes)
        started = threading.Event()

        def blocking_download(url, opts, job_id):
            started.set()
            while not dl.is_cancelled:
                time.sleep(0.005)
            return False

        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = blocking_download
        dl.start(_params(output_folder=str(tmp_path), whole_video=True))
        assert started.wait(5)
        dl.cancel()
        dl._thread.join(timeout=5)
        assert not dl._thread.is_alive()
        assert finishes == [(False, "Zrušeno")]

        dl2 = Downloader({})
        finishes2 = []
        self._hook(dl2, finishes=finishes2)
        dl2._get_title = lambda url: "Mock Title"

        def fake_download2(url, opts, job_id):
            job_dir = Path(opts["_job_dir"])
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "Mock Title.mp4").write_text("x")
            return True

        dl2._download_with_ytdlp = fake_download2
        dl2.start(_params(output_folder=str(tmp_path), whole_video=True))
        dl2._thread.join(timeout=5)
        assert finishes2 == [(True, "Úspěch")]

    def test_cancel_during_ffmpeg_returns_zruseno(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        finishes = []
        self._hook(dl, finishes=finishes)
        dl._get_title = lambda url: "Mock Title"
        dl._download_with_ytdlp = lambda url, opts, job_id: True
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        source = job_dir / "Src.mp4"
        source.write_text("x")

        def cut(*a, **k):
            dl.cancel()
            return None

        dl._cut_with_ffmpeg = cut
        dl._download_worker(
            _params(
                output_folder=str(output),
                whole_video=False,
                start_time="00:00",
                end_time="00:05",
                end_option="Manuální čas",
            ),
            "j1",
        )
        assert finishes == [(False, "Zrušeno")]
        assert not job_dir.exists()

    def test_cancel_during_active_download_ends_worker(self, tmp_path, monkeypatch):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        finishes, logs = [], []
        self._hook(dl, logs=logs, finishes=finishes)
        dl._get_title = lambda url: "Mock Title"
        entered = threading.Event()

        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts

            def download(self, urls):
                entered.set()
                while not dl.is_cancelled:
                    time.sleep(0.005)
                self.opts["progress_hooks"][0]({"status": "downloading"})

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        output = tmp_path / "out"
        dl.start(_params(output_folder=str(output), whole_video=True))
        assert entered.wait(5)
        dl.cancel()
        dl._thread.join(timeout=5)
        assert finishes == [(False, "Zrušeno")]
        assert not dl.is_busy()
        assert not (output / JOBS_DIR_NAME / "j1").exists()


class TestDownloadWithYtdlp:
    def _make_dl(self, statuses=None, logs=None):
        dl = Downloader({})
        dl.on_status = lambda jid, t, c: statuses.append((t, c)) if statuses is not None else None
        dl.on_log = lambda t: logs.append(t) if logs is not None else None
        return dl

    def test_success(self, monkeypatch):
        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts

            def download(self, urls):
                assert urls == ["https://example.com/v"]

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        dl = self._make_dl()
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is True

    def test_cancel_error(self, monkeypatch, tmp_path):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise yt_dlp.utils.DownloadError("Stahování zrušeno uživatelem")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        dl = self._make_dl()
        opts = {
            "outtmpl": str(tmp_path / "X [job].%(ext)s"),
            "_job_id": "job",
            "_job_dir": str(tmp_path / ".jobs" / "job"),
        }
        assert dl._download_with_ytdlp("https://example.com/v", opts, "j1") is False

    def test_download_cancelled_exception(self, monkeypatch, tmp_path):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise yt_dlp.utils.DownloadCancelled("Stahování zrušeno uživatelem")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        logs = []
        dl = self._make_dl(logs=logs)
        opts = {
            "outtmpl": str(tmp_path / "X [job].%(ext)s"),
            "_job_id": "job",
            "_job_dir": str(tmp_path / ".jobs" / "job"),
        }
        assert dl._download_with_ytdlp("https://example.com/v", opts, "j1") is False
        assert any("zrušeno" in line.lower() for line in logs)
        assert not any("Neočekávaná chyba" in line for line in logs)
        assert not (tmp_path / ".jobs" / "job").exists()

    def test_cancelled_before_attempt_skips_ytdlp(self, monkeypatch):
        calls = {"n": 0}

        class FakeYDL:
            def __init__(self, opts):
                calls["n"] += 1

            def download(self, urls):
                raise AssertionError("download should not run")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        dl = self._make_dl()
        dl.cancel()
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is False
        assert calls["n"] == 0

    def test_download_cancelled_via_hook(self, monkeypatch, tmp_path):
        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts

            def download(self, urls):
                with pytest.raises(yt_dlp.utils.DownloadCancelled):
                    self.opts["progress_hooks"][0]({"status": "downloading"})

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        dl = self._make_dl()
        dl.cancel()
        opts = _build_ydl_opts(_params(), {}, lambda d: dl._progress_hook("j1", d))
        opts["_job_dir"] = str(tmp_path / ".jobs" / "j1")
        assert dl._download_with_ytdlp("https://example.com/v", opts, "j1") is False

    def test_cancel_between_attempts_skips_retry(self, monkeypatch):
        calls = {"n": 0}

        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                calls["n"] += 1
                raise yt_dlp.utils.DownloadError("Unable to download JSON metadata: HTTP Error 403: Forbidden")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        dl = self._make_dl()
        dl.cancel()
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is False
        assert calls["n"] == 0

    def test_subtitles_warning_is_success(self, monkeypatch):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise yt_dlp.utils.DownloadError("Unable to download video subtitles: no")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        statuses = []
        dl = self._make_dl(statuses=statuses)
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is True
        assert any("Titulky staženy" in t for t, _ in statuses)

    def test_forbidden_error(self, monkeypatch):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise yt_dlp.utils.DownloadError("HTTP Error 403: Forbidden")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        statuses = []
        dl = self._make_dl(statuses=statuses)
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is False
        assert any("403" in t for t, _ in statuses)

    def test_transient_403_is_retried(self, monkeypatch):
        calls = {"n": 0}

        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                calls["n"] += 1
                if calls["n"] < 2:
                    raise yt_dlp.utils.DownloadError("Unable to download JSON metadata: HTTP Error 403: Forbidden")
                return True

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        dl = self._make_dl()
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is True
        assert calls["n"] == 2

    def test_generic_download_error(self, monkeypatch):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise yt_dlp.utils.DownloadError("Some random failure")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        statuses = []
        dl = self._make_dl(statuses=statuses)
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is False
        assert any("Stahování selhalo" in t for t, _ in statuses)

    def test_unexpected_exception(self, monkeypatch):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise ValueError("boom")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        logs = []
        dl = self._make_dl(logs=logs)
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is False
        assert any("Neočekávaná chyba" in line for line in logs)


class TestIsTransientError:
    @pytest.mark.parametrize(
        "err",
        [
            "HTTP Error 403: Forbidden",
            "HTTP Error 408: Request Timeout",
            "HTTP Error 410: Gone",
            "HTTP Error 429: Too Many Requests",
            "HTTP Error 500",
            "HTTP Error 503",
            "timed out",
            "Connection reset by peer",
            "rate limit reached",
            "temporary failure in name resolution",
        ],
    )
    def test_transient(self, err):
        assert Downloader._is_transient_error(err) is True

    @pytest.mark.parametrize(
        "err",
        [
            "Some random failure",
            "Video is not available",
            "HTTP Error 404: Not Found",
        ],
    )
    def test_not_transient(self, err):
        assert Downloader._is_transient_error(err) is False


class TestReportDownloadError:
    def _make_dl(self):
        dl = Downloader({})
        statuses = []
        dl.on_status = lambda jid, t, c: statuses.append(t)
        return dl, statuses

    def test_kick_deleted_or_unavailable(self):
        dl, statuses = self._make_dl()
        dl._report_download_error(
            "ERROR: [kick:vod] abc123: Video is not available in your country ... not found (deleted or unavailable)",
            "j1",
        )
        assert statuses == ["Video není dostupné nebo bylo smazáno."]

    def test_403_message(self):
        dl, statuses = self._make_dl()
        dl._report_download_error("ERROR: HTTP Error 403: Forbidden", "j1")
        assert any("403" in s for s in statuses)

    def test_404_message(self):
        dl, statuses = self._make_dl()
        dl._report_download_error("ERROR: 404 Not Found", "j1")
        assert statuses == ["Video není dostupné nebo bylo smazáno."]

    @pytest.mark.parametrize("err", ["HTTP Error 429: Too Many Requests", "rate limit reached", "HTTP Error 410: Gone"])
    def test_rate_limit_message(self, err):
        dl, statuses = self._make_dl()
        dl._report_download_error(err, "j1")
        assert statuses == [
            "Dočasné omezení ze strany serveru (příliš mnoho požadavků). Počkej chvíli a zkus to znovu."
        ]

    def test_fallback_message(self):
        dl, statuses = self._make_dl()
        dl._report_download_error("ERROR: Something else went wrong", "j1")
        assert statuses[0].startswith("Stahování selhalo")


class TestCleanupOutput:
    def test_no_job_dir_noop(self):
        dl = Downloader({})
        dl._cleanup_output({})
        dl._cleanup_output({"outtmpl": "/tmp/x"})

    def test_removes_job_dir_regardless_of_size(self, tmp_path):
        dl = Downloader({})
        logs = []
        dl.on_log = lambda t: logs.append(t)
        job_dir = tmp_path / "X" / JOBS_DIR_NAME / "abc"
        job_dir.mkdir(parents=True)
        (job_dir / "X [abc].part").write_text("y")
        (job_dir / "X [abc].mp4").write_bytes(b"0" * (2 * 1024 * 1024))
        other = tmp_path / "other.txt"
        other.write_text("z")
        dl._cleanup_output({"_job_dir": str(job_dir)})
        assert not job_dir.exists()
        assert other.exists()
        assert any("Smazán neúplný pracovní adresář" in line for line in logs)

    def test_missing_dir_noop(self, tmp_path):
        dl = Downloader({})
        dl._cleanup_output({"_job_dir": str(tmp_path / "missing" / "abc")})


class TestSafeCrf:
    @pytest.mark.parametrize("value,expected", [("30", 30), ("55", 23), ("-3", 23), ("abc", 23), (None, 23), (5, 5)])
    def test_values(self, value, expected):
        assert Downloader._safe_crf(value) == expected


class TestProcessHelpers:
    class FakeProc:
        def __init__(self, pid=123):
            self.pid = pid
            self.terminated = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-specific")
    def test_kill_linux_fallback(self, monkeypatch):
        proc = self.FakeProc(123)
        monkeypatch.setattr(dl_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(dl_mod.os, "getpgid", lambda pid: (_ for _ in ()).throw(ProcessLookupError()))
        dl_mod._kill_process(proc)
        assert proc.terminated

    def test_kill_windows(self, monkeypatch):
        proc = self.FakeProc(123)
        calls = []
        monkeypatch.setattr(dl_mod.platform, "system", lambda: "Windows")

        def fake_run(args, **kwargs):
            calls.append(args)
            return None

        monkeypatch.setattr(dl_mod.subprocess, "run", fake_run)
        dl_mod._kill_process(proc)
        assert calls[0] == ["taskkill", "/F", "/T", "/PID", "123"]

    def test_kill_swallows_exceptions(self, monkeypatch):
        proc = self.FakeProc(123)
        monkeypatch.setattr(dl_mod.platform, "system", lambda: "Windows")

        def fake_run(args, **kwargs):
            raise OSError("nope")

        monkeypatch.setattr(dl_mod.subprocess, "run", fake_run)
        dl_mod._kill_process(proc)

    def test_track_and_cleanup(self, monkeypatch):
        proc = self.FakeProc(123)
        dl_mod._track_process(proc)
        monkeypatch.setattr(dl_mod, "_kill_process", lambda p: None)
        dl_mod._cleanup_child_processes()
        assert proc not in dl_mod._CHILD_PROCESSES


def _hls_fmt(fmt_id, url, height=None, vcodec="h264", acodec="aac", tbr=1000, protocol="m3u8_native", headers=None):
    fmt = {
        "format_id": fmt_id,
        "url": url,
        "protocol": protocol,
        "height": height,
        "vcodec": vcodec,
        "acodec": acodec,
        "tbr": tbr,
    }
    if headers is not None:
        fmt["http_headers"] = headers
    return fmt


class TestRangedHls:
    def test_can_ranged_hls_kick(self):
        assert _can_ranged_hls("https://kick.com/ch/videos/123")

    def test_can_ranged_hls_twitch(self):
        assert _can_ranged_hls("https://www.twitch.tv/videos/123")

    def test_can_ranged_hls_youtube_false(self):
        assert not _can_ranged_hls("https://www.youtube.com/watch?v=abc")

    def test_can_ranged_hls_unknown_false(self):
        assert not _can_ranged_hls("https://vimeo.com/123")

    def test_select_hls_best(self):
        info = {
            "formats": [
                _hls_fmt("v-1080", "https://x/v1080.m3u8", height=1080),
                _hls_fmt("v-720", "https://x/v720.m3u8", height=720),
            ]
        }
        video, audio = _select_hls_formats(info, QUALITY_BEST)
        assert video["format_id"] == "v-1080"
        assert audio is None

    def test_select_hls_by_quality_prefers_at_most(self):
        info = {
            "formats": [
                _hls_fmt("v-1080", "https://x/v1080.m3u8", height=1080),
                _hls_fmt("v-720", "https://x/v720.m3u8", height=720),
                _hls_fmt("v-480", "https://x/v480.m3u8", height=480),
            ]
        }
        video, _ = _select_hls_formats(info, "720p")
        assert video["format_id"] == "v-720"
        video, _ = _select_hls_formats(info, "9999p")
        assert video["format_id"] == "v-1080"

    def test_select_hls_separate_audio(self):
        info = {
            "formats": [
                _hls_fmt("v-1080", "https://x/v1080.m3u8", height=1080, acodec="none"),
                _hls_fmt("a-256", "https://x/a256.m3u8", height=None, vcodec="none", tbr=256),
                _hls_fmt("a-128", "https://x/a128.m3u8", height=None, vcodec="none", tbr=128),
            ]
        }
        video, audio = _select_hls_formats(info, QUALITY_BEST)
        assert video["format_id"] == "v-1080"
        assert audio["format_id"] == "a-256"

    def test_select_hls_muxed_ignores_separate_audio(self):
        info = {
            "formats": [
                _hls_fmt("v-1080", "https://x/v1080.m3u8", height=1080, acodec="aac"),
                _hls_fmt("a-256", "https://x/a256.m3u8", height=None, vcodec="none", tbr=256),
            ]
        }
        video, audio = _select_hls_formats(info, QUALITY_BEST)
        assert video["format_id"] == "v-1080"
        assert audio is None

    def test_select_hls_no_hls_formats(self):
        info = {"formats": [_hls_fmt("http", "https://x/v.mp4", protocol="https")]}
        assert _select_hls_formats(info, QUALITY_BEST) == (None, None)

    def test_select_hls_no_video_formats(self):
        info = {"formats": [_hls_fmt("a-128", "https://x/a.m3u8", height=None, vcodec="none")]}
        assert _select_hls_formats(info, QUALITY_BEST) == (None, None)

    def test_select_hls_none_info(self):
        assert _select_hls_formats(None, QUALITY_BEST) == (None, None)

    def test_ranged_output_name_with_range(self):
        name = _ranged_output_name("Velký stream", "720p", "00:01:30", "00:02:30", "Manuální čas")
        assert name == "Velký stream [720p] [00h01m30s - 00h02m30s].mp4"

    def test_ranged_output_name_to_end(self):
        name = _ranged_output_name("Stream", QUALITY_BEST, "00:01:00", "00:00", "Do konce videa")
        assert name == "Stream [00h01m00s-inf].mp4"

    def test_ranged_output_name_very_long_title_capped(self):
        long_title = "N" * 300
        name = _ranged_output_name(long_title, "1080p", "00:01:30", "00:02:30", "Manuální čas")
        assert name.endswith(".mp4")
        assert len(name) <= 255
        assert name.startswith("N" * 150)

    def test_build_ranged_cmd_copy(self):
        video = _hls_fmt("v", "https://x/v.m3u8", headers={"User-Agent": "UA", "Referer": "https://kick.com/"})
        cmd = _build_ranged_cmd(
            video, None, "00:00:30", "00:01:00", "Manuální čas", False, 23, "fast", Path("/o/a.mp4"), "ffmpeg"
        )
        assert cmd[0] == "ffmpeg"
        assert cmd[1] == "-y"
        assert cmd[2] == "-ss"
        assert cmd[3] == "00:00:30"
        assert "User-Agent: UA\r\nReferer: https://kick.com/\r\n" in cmd
        assert cmd[cmd.index("-i") + 1] == "https://x/v.m3u8"
        assert cmd[cmd.index("-t") + 1] == "30"
        assert "-c" in cmd
        assert "copy" in cmd
        assert "-bsf:a" in cmd
        assert cmd[-3:-1] == ["-movflags", "+faststart"]

    def test_build_ranged_cmd_to_end(self):
        video = _hls_fmt("v", "https://x/v.m3u8")
        cmd = _build_ranged_cmd(
            video, None, "00:00:30", "00:00", "Do konce videa", False, 23, "fast", Path("/o/a.mp4"), "ffmpeg"
        )
        assert "-t" not in cmd

    def test_build_ranged_cmd_two_inputs(self):
        video = _hls_fmt("v", "https://x/v.m3u8", acodec="none")
        audio = _hls_fmt("a", "https://x/a.m3u8", vcodec="none")
        cmd = _build_ranged_cmd(
            video, audio, "00:00", "00:05", "Manuální čas", True, 20, "slow", Path("/o/a.mp4"), "ffmpeg"
        )
        inputs = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-i"]
        assert inputs == ["https://x/v.m3u8", "https://x/a.m3u8"]
        assert "-c:v" in cmd and "libx264" in cmd
        assert "-crf" in cmd and "20" in cmd
        assert "-preset" in cmd and "slow" in cmd

    def test_build_ranged_cmd_no_headers(self):
        video = _hls_fmt("v", "https://x/v.m3u8")
        cmd = _build_ranged_cmd(
            video, None, "00:00", "00:05", "Manuální čas", False, 23, "fast", Path("/o/a.mp4"), "ffmpeg"
        )
        assert "-headers" not in cmd


class TestRangedDownloadWorker:
    def _hook(self, dl, statuses=None, logs=None, finishes=None):
        dl.on_status = lambda jid, t, c: statuses.append(t) if statuses is not None else None
        dl.on_log = lambda t: logs.append(t) if logs is not None else None
        dl.on_finish = lambda jid, s, m: finishes.append((s, m)) if finishes is not None else None

    def _kick_params(self, output, **overrides):
        return _params(
            url="https://kick.com/ch/videos/abc",
            output_folder=str(output),
            whole_video=False,
            start_time="00:00",
            end_time="00:05",
            end_option="Manuální čas",
            **overrides,
        )

    def test_kick_trim_uses_ranged_download(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses, logs, finishes = [], [], []
        self._hook(dl, statuses=statuses, logs=logs, finishes=finishes)
        dl._get_title = lambda url: "Kick Stream"
        dl._download_with_ytdlp = lambda url, opts, job_id: None
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)

        def fake_ranged(params, url, job_id, job_dir):
            path = job_dir / "Kick Stream [00h00m00s - 00h00m05s].mp4"
            path.write_text("x")
            return path

        dl._ranged_download = fake_ranged
        dl._download_worker(self._kick_params(output), "j1")
        assert finishes == [(True, "Úspěch")]
        assert any("HLS segmentů" in log for log in logs)
        assert (output / "Kick Stream [00h00m00s - 00h00m05s].mp4").exists()

    def test_kick_trim_ranged_failure_falls_back_to_full(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses, logs, finishes = [], [], []
        self._hook(dl, statuses=statuses, logs=logs, finishes=finishes)
        dl._get_title = lambda url: "Kick Stream"
        full_download_calls = []

        def fake_full(url, opts, job_id):
            full_download_calls.append(job_id)
            job_dir = Path(opts["_job_dir"])
            (job_dir / "Kick Stream.mp4").write_text("x")
            return True

        dl._download_with_ytdlp = fake_full
        dl._ranged_download = lambda params, url, job_id, job_dir: None
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        dl._download_worker(self._kick_params(output), "j1")
        assert finishes == [(True, "Úspěch")]
        assert full_download_calls == ["j1"]
        assert any("lokálně" in log for log in logs)
        assert (output / "Kick Stream.mp4").exists()

    def test_youtube_trim_skips_ranged(self, tmp_path):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        dl = Downloader({})
        statuses = []
        self._hook(dl, statuses=statuses)
        dl._get_title = lambda url: "YT"
        called = {"ranged": False}

        def fake_ranged(*a, **k):
            called["ranged"] = True
            return None

        dl._ranged_download = fake_ranged

        def fake_full(url, opts, job_id):
            job_dir = Path(opts["_job_dir"])
            (job_dir / "YT.mp4").write_text("x")
            return True

        dl._download_with_ytdlp = fake_full
        output = tmp_path / "out"
        job_dir = output / JOBS_DIR_NAME / "j1"
        job_dir.mkdir(parents=True)
        dl._download_worker(
            _params(
                output_folder=str(output),
                whole_video=False,
                start_time="00:00",
                end_time="00:05",
                end_option="Manuální čas",
            ),
            "j1",
        )
        assert called["ranged"] is False
        assert (output / "YT.mp4").exists()
