"""Auditové testy pro nekryté větve stahovac.core.downloader (coverage report)."""

import subprocess
from pathlib import Path

import yt_dlp

import stahovac.core.downloader as dl_mod
from stahovac.core.downloader import Downloader, _closest_height_format, _fmt_timestamp, _unique_dest
from stahovac.core.metadata import MetadataService
from stahovac.models import DownloadParams, VideoMetadata


class TestFmtTimestamp:
    def test_three_parts(self):
        assert _fmt_timestamp("01:02:03") == "01h02m03s"

    def test_two_parts(self):
        assert _fmt_timestamp("01:30") == "01m30s"

    def test_one_part(self):
        assert _fmt_timestamp("90") == "90s"


class TestClosestHeightFormat:
    def test_empty_videos_returns_none(self):
        assert _closest_height_format([], 720) is None


class TestSelectHlsInvalidQuality:
    def test_invalid_quality_falls_back_to_best(self):
        from stahovac.core.downloader import _select_hls_formats

        def _fmt(fid, height):
            return {
                "format_id": fid,
                "url": f"https://x/{fid}.m3u8",
                "protocol": "m3u8_native",
                "height": height,
                "vcodec": "h264",
                "acodec": "aac",
                "tbr": 1000,
            }

        info = {"formats": [_fmt("v-1080", 1080), _fmt("v-720", 720), _fmt("v-480", 480)]}
        video, _ = _select_hls_formats(info, "not-a-quality")
        assert video["format_id"] == "v-1080"


class TestUniqueDestFallback:
    def test_returns_dest_after_exhausting_counters(self, tmp_path):
        (tmp_path / "a.mp4").write_text("x")
        for i in range(1, 1000):
            (tmp_path / f"a ({i}).mp4").write_text("x")
        assert _unique_dest(tmp_path, "a.mp4") == tmp_path / "a.mp4"


class TestKillProcess:
    class FakeProc:
        def __init__(self, pid=123):
            self.pid = pid
            self.terminated = 0
            self.killed = 0
            self.waited = 0
            self._wait_failures = 0

        def terminate(self):
            self.terminated += 1

        def kill(self):
            self.killed += 1

        def wait(self, timeout=None):
            self.waited += 1
            if self._wait_failures:
                self._wait_failures -= 1
                raise subprocess.TimeoutExpired(["cmd"], timeout)
            return 0

    def test_linux_success(self, monkeypatch):
        proc = self.FakeProc(123)
        monkeypatch.setattr(dl_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(dl_mod.os, "getpgid", lambda pid: 999)
        killed = []
        monkeypatch.setattr(dl_mod.os, "killpg", lambda *a: killed.append(a))
        dl_mod._kill_process(proc)
        assert killed == [(999, dl_mod.signal.SIGTERM)]
        assert proc.waited == 1

    def test_linux_terminate_then_kill(self, monkeypatch):
        proc = self.FakeProc(123)
        proc._wait_failures = 1
        monkeypatch.setattr(dl_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(dl_mod.os, "getpgid", lambda pid: (_ for _ in ()).throw(ProcessLookupError()))
        dl_mod._kill_process(proc)
        assert proc.terminated == 1
        assert proc.killed == 1

    def test_swallows_wait_errors(self, monkeypatch):
        proc = self.FakeProc(123)

        def bad_wait(timeout=None):
            raise subprocess.TimeoutExpired(["cmd"], timeout)

        proc.wait = bad_wait
        monkeypatch.setattr(dl_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(dl_mod.os, "getpgid", lambda pid: (_ for _ in ()).throw(OSError("boom")))
        dl_mod._kill_process(proc)
        assert proc.terminated == 1


class TestMetadataProperty:
    def test_returns_internal_service(self):
        dl = Downloader({})
        assert dl.metadata is dl._metadata


class TestGetTitle:
    def test_returns_cached_title(self):
        dl = Downloader({})
        meta = VideoMetadata(title="Cached", uploader="u", duration=0, thumbnail="", description="")
        svc = MetadataService()
        svc._add_to_cache("https://example.com/v", meta)
        dl._metadata = svc
        assert dl._get_title("https://example.com/v") == "Cached"

    def test_returns_url_when_no_metadata(self):
        dl = Downloader({})
        dl._metadata.get_cached = lambda url: None
        dl._metadata.fetch_sync = lambda *a, **k: None
        assert dl._get_title("https://example.com/v") == "https://example.com/v"


class _FakeCancelEvent:
    def __init__(self, wait_result=False, is_set_result=False):
        self._wait = wait_result
        self._is_set = is_set_result

    def is_set(self):
        return self._is_set

    def wait(self, timeout=None):
        return self._wait

    def clear(self):
        pass

    def set(self):
        pass


class TestDownloadWithYtdlpExtraBranches:
    def _make_dl(self, statuses=None, logs=None):
        dl = Downloader({})
        dl.on_status = lambda jid, t, c: statuses.append(t) if statuses is not None else None
        dl.on_log = lambda t: logs.append(t) if logs is not None else None
        return dl

    def test_cancel_during_retry_wait(self, monkeypatch, tmp_path):
        calls = {"n": 0}

        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                calls["n"] += 1
                raise yt_dlp.utils.DownloadError("Unable to download JSON metadata: HTTP Error 403: Forbidden")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        dl = self._make_dl(logs=[])
        dl._cancel_event = _FakeCancelEvent(wait_result=True)
        opts = {"_job_dir": str(tmp_path / ".jobs" / "j1")}
        assert dl._download_with_ytdlp("https://example.com/v", opts, "j1") is False
        assert calls["n"] == 1

    def test_youtubedl_error_branch(self, monkeypatch):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise yt_dlp.utils.YoutubeDLError("generic ydl problem")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        statuses = []
        dl = self._make_dl(statuses=statuses)
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is False
        assert any("Chyba při stahování" in t for t in statuses)

    def test_retries_exhausted(self, monkeypatch):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def download(self, urls):
                raise yt_dlp.utils.DownloadError("HTTP Error 500: Internal Server Error")

        monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYDL)
        statuses = []
        dl = self._make_dl(statuses=statuses)
        dl._cancel_event = _FakeCancelEvent(wait_result=False)
        assert dl._download_with_ytdlp("https://example.com/v", {}, "j1") is False
        assert any(t.startswith("Stahování selhalo") for t in statuses)


class TestReportDownloadErrorRegisteredUsers:
    def test_registered_users_message(self):
        dl = Downloader({})
        statuses = []
        dl.on_status = lambda jid, t, c: statuses.append(t)
        dl._report_download_error("ERROR: video requires registered users", "j1")
        assert statuses == ["Video vyžaduje přihlášení – použij cookies."]


class TestRangedDownload:
    def _make_dl(self, logs=None, statuses=None):
        dl = Downloader({})
        dl.on_log = lambda t: logs.append(t) if logs is not None else None
        dl.on_status = lambda jid, t, c: statuses.append(t) if statuses is not None else None
        return dl

    def _kick_params(self):
        return DownloadParams(
            url="https://kick.com/ch/videos/abc",
            quality="720p",
            format_choice="Video + audio (MP4)",
            output_folder="/tmp/out",
            whole_video=False,
            start_time="00:00",
            end_time="00:05",
            end_option="Manuální čas",
        )

    def test_no_ffmpeg_returns_none(self, monkeypatch):
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: None)
        dl = self._make_dl(logs=[])
        assert dl._ranged_download(self._kick_params(), "https://kick.com/ch/videos/abc", "j1", Path("/tmp/x")) is None

    def test_cancelled_after_fetch_info(self, monkeypatch):
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: Path("/opt/ffmpeg/bin/ffmpeg"))
        dl = self._make_dl()
        dl._metadata.fetch_info = lambda *a, **k: {"formats": []}
        dl.is_cancelled = True
        assert dl._ranged_download(self._kick_params(), "https://kick.com/ch/videos/abc", "j1", Path("/tmp/x")) is None

    def test_no_video_format(self, monkeypatch):
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: Path("/opt/ffmpeg/bin/ffmpeg"))
        monkeypatch.setattr(dl_mod, "_select_hls_formats", lambda info, quality: (None, None))
        logs = []
        dl = self._make_dl(logs=logs)
        dl._metadata.fetch_info = lambda *a, **k: {"formats": []}
        result = dl._ranged_download(self._kick_params(), "https://kick.com/ch/videos/abc", "j1", Path("/tmp/x"))
        assert result is None
        assert any("HLS formát" in line for line in logs)

    def _patch_success(self, monkeypatch, tmp_path, job_dir):
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: Path("/opt/ffmpeg/bin/ffmpeg"))
        monkeypatch.setattr(
            dl_mod, "_select_hls_formats", lambda info, quality: ({"url": "https://x/v.m3u8"}, None)
        )
        monkeypatch.setattr(dl_mod, "_build_ranged_cmd", lambda *a, **k: ["ffmpeg", "arg"])
        monkeypatch.setattr(dl_mod.subprocess, "Popen", lambda *a, **k: object())
        dl = self._make_dl()
        dl._metadata.fetch_info = lambda *a, **k: {"formats": []}

        def run_ffmpeg(proc, estimated, re_encode, job_id):
            temp = job_dir / "ranged.tmp.mp4"
            temp.write_text("x")
            return True

        dl._run_ffmpeg = run_ffmpeg
        dl._get_title = lambda url: "Stream"
        return dl

    def test_success_replaces_temp(self, monkeypatch, tmp_path):
        job_dir = tmp_path / ".jobs" / "j1"
        job_dir.mkdir(parents=True)
        dl = self._patch_success(monkeypatch, tmp_path, job_dir)
        out = dl._ranged_download(self._kick_params(), "https://kick.com/ch/videos/abc", "j1", job_dir)
        assert out is not None
        assert out.exists()
        assert out.name == "Stream [720p] [00h00m00s - 00h00m05s].mp4"

    def test_failure_unlinks_temp(self, monkeypatch, tmp_path):
        job_dir = tmp_path / ".jobs" / "j1"
        job_dir.mkdir(parents=True)
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: Path("/opt/ffmpeg/bin/ffmpeg"))
        monkeypatch.setattr(dl_mod, "_select_hls_formats", lambda info, quality: ({"url": "x"}, None))
        monkeypatch.setattr(dl_mod, "_build_ranged_cmd", lambda *a, **k: ["ffmpeg"])
        monkeypatch.setattr(dl_mod.subprocess, "Popen", lambda *a, **k: object())
        dl = self._make_dl()
        dl._metadata.fetch_info = lambda *a, **k: {"formats": []}
        dl._run_ffmpeg = lambda *a, **k: False
        dl._get_title = lambda url: "Stream"
        assert dl._ranged_download(self._kick_params(), "https://kick.com/ch/videos/abc", "j1", job_dir) is None
        assert not (job_dir / "ranged.tmp.mp4").exists()

    def test_cancelled_after_get_title(self, monkeypatch, tmp_path):
        job_dir = tmp_path / ".jobs" / "j1"
        job_dir.mkdir(parents=True)
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: Path("/opt/ffmpeg/bin/ffmpeg"))
        monkeypatch.setattr(dl_mod, "_select_hls_formats", lambda info, quality: ({"url": "x"}, None))
        monkeypatch.setattr(dl_mod, "_build_ranged_cmd", lambda *a, **k: ["ffmpeg"])
        monkeypatch.setattr(dl_mod.subprocess, "Popen", lambda *a, **k: object())
        dl = self._make_dl()
        dl._metadata.fetch_info = lambda *a, **k: {"formats": []}
        dl._run_ffmpeg = lambda *a, **k: True

        def get_title(url):
            dl.cancel()
            return "Stream"

        dl._get_title = get_title
        assert dl._ranged_download(self._kick_params(), "https://kick.com/ch/videos/abc", "j1", job_dir) is None

    def test_cancelled_after_ffmpeg_unlinks_temp(self, monkeypatch, tmp_path):
        job_dir = tmp_path / ".jobs" / "j1"
        job_dir.mkdir(parents=True)
        monkeypatch.setattr(dl_mod, "find_ffmpeg", lambda: Path("/opt/ffmpeg/bin/ffmpeg"))
        monkeypatch.setattr(dl_mod, "_select_hls_formats", lambda info, quality: ({"url": "x"}, None))
        monkeypatch.setattr(dl_mod, "_build_ranged_cmd", lambda *a, **k: ["ffmpeg"])
        monkeypatch.setattr(dl_mod.subprocess, "Popen", lambda *a, **k: object())
        dl = self._make_dl()
        dl._metadata.fetch_info = lambda *a, **k: {"formats": []}

        def run_ffmpeg(proc, estimated, re_encode, job_id):
            (job_dir / "ranged.tmp.mp4").write_text("x")
            dl.cancel()
            return True

        dl._run_ffmpeg = run_ffmpeg
        dl._get_title = lambda url: "Stream"
        assert dl._ranged_download(self._kick_params(), "https://kick.com/ch/videos/abc", "j1", job_dir) is None
        assert not (job_dir / "ranged.tmp.mp4").exists()


class TestRunFfmpegMoreBranches:
    def _make_proc(self, stderr=None, wait=None):
        class FakeStdErr:
            def __init__(self, src):
                self._src = list(src)

            def readline(self):
                if not self._src:
                    return ""
                return self._src.pop(0)

        class FakeProc:
            def __init__(self):
                self.stderr = stderr if stderr is not None else FakeStdErr([])
                self.returncode = 0
                self._wait = wait

            def wait(self, timeout=None):
                if self._wait is not None:
                    return self._wait(timeout)
                return 0

        return FakeProc()

    def test_stderr_readline_raises_oserror(self):
        class ErrStdErr:
            def readline(self):
                raise OSError("closed")

        proc = self._make_proc(stderr=ErrStdErr())
        dl = Downloader({})
        assert dl._run_ffmpeg(proc, None, False, "j1") is True

    def test_timeout_kills_process(self, monkeypatch):
        calls = {"n": 0}

        def fake_time():
            calls["n"] += 1
            return 0.0 if calls["n"] == 1 else 99999.0

        monkeypatch.setattr(dl_mod.time, "time", fake_time)
        killed = []
        monkeypatch.setattr(dl_mod, "_kill_process", lambda p: killed.append(p))
        dl = Downloader({})
        logs = []
        dl.on_log = lambda t: logs.append(t)
        assert dl._run_ffmpeg(self._make_proc(), None, False, "j1") is False
        assert killed
        assert any("přesáhlo" in line for line in logs)

    def test_wait_timeout_kills_process(self):
        proc = self._make_proc(wait=lambda timeout: (_ for _ in ()).throw(subprocess.TimeoutExpired(["ffmpeg"], 10)))
        killed = []
        dl = Downloader({})
        dl_mod._kill_process = lambda p: killed.append(p)
        assert dl._run_ffmpeg(proc, None, False, "j1") is False
        assert killed


class TestFinishMessages:
    def test_mp3_message(self, tmp_path, monkeypatch):
        dl = Downloader({})
        statuses = []
        dl.on_status = lambda jid, t, c: statuses.append(t)
        dl._finish_success("j1", "T", "u", None, "Pouze zvuk (MP3)")
        assert any("Zvuk (MP3)" in s for s in statuses)

    def test_subs_message(self):
        dl = Downloader({})
        statuses = []
        dl.on_status = lambda jid, t, c: statuses.append(t)
        dl._finish_success("j1", "T", "u", None, "Pouze titulky (SRT)")
        assert any("Titulky (SRT)" in s for s in statuses)
