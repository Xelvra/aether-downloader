import io
import json
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import pytest

import stahovac.core.ffmpeg as ffmpeg_mod
from stahovac.core.ffmpeg import (
    EVERMEET_INFO_URL,
    FfmpegInstallError,
    _download,
    _extract,
    _find_binaries,
    _http_get,
    _resolve_download_url,
    _smoke_test,
    bin_dir,
    download_and_install,
    ffmpeg_dir,
    find_ffmpeg,
    get_download_url,
    get_ffmpeg_version,
    install_in_progress,
    wait_until_ready,
)
from stahovac.utils.paths import set_base_dir


class FakeResponse:
    def __init__(self, data: bytes, total: int | None = None):
        self._data = data
        self._offset = 0
        self.headers = {"Content-Length": str(total) if total is not None else ""}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int = -1):
        if self._offset >= len(self._data):
            return b""
        chunk = self._data[self._offset : self._offset + size] if size >= 0 else self._data[self._offset :]
        self._offset += len(chunk)
        return chunk


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _make_tar_xz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_base_dir():
    yield
    set_base_dir(None)


@pytest.fixture
def base(tmp_path):
    set_base_dir(tmp_path)
    yield tmp_path
    set_base_dir(None)


class TestBinDir:
    def test_under_base_dir(self, base):
        assert bin_dir() == base / "bin"


class TestGetDownloadUrl:
    def test_linux_amd64(self):
        assert get_download_url("Linux", "x86_64").endswith("amd64-static.tar.xz")

    def test_linux_arm64(self):
        assert get_download_url("Linux", "aarch64").endswith("arm64-static.tar.xz")

    def test_linux_armv7(self):
        assert get_download_url("Linux", "armv7l").endswith("armhf-static.tar.xz")

    def test_linux_unsupported_arch(self):
        assert get_download_url("Linux", "riscv64") is None

    def test_windows_x64(self):
        assert get_download_url("Windows", "AMD64").endswith("ffmpeg-release-essentials.zip")

    def test_windows_unsupported_arch(self):
        assert get_download_url("Windows", "ARM64") is None

    def test_macos_uses_evermeet_api(self):
        assert get_download_url("Darwin", "arm64") == EVERMEET_INFO_URL

    def test_unknown_system(self):
        assert get_download_url("AmigaOS", "x86_64") is None

    def test_defaults_to_real_platform(self):
        result = get_download_url()
        assert result is None or isinstance(result, str)


class TestFindFfmpeg:
    def test_path_first(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
        assert find_ffmpeg() == Path("/usr/bin/ffmpeg").resolve()

    def test_local_fallback(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        (base / "bin").mkdir()
        binary = base / "bin" / "ffmpeg"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        assert find_ffmpeg() == binary.resolve()

    def test_none_when_missing(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(ffmpeg_mod, "_MACOS_HOMEBREW_PATHS", ())
        assert find_ffmpeg() is None

    def test_local_ignored_when_not_executable(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(ffmpeg_mod, "_MACOS_HOMEBREW_PATHS", ())
        (base / "bin").mkdir()
        (base / "bin" / "ffmpeg").write_text("x")
        monkeypatch.setattr(ffmpeg_mod.os, "access", lambda path, mode: False)
        assert find_ffmpeg() is None

    def test_macos_homebrew_fallback(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(ffmpeg_mod.sys, "platform", "darwin")
        binary = base / "homebrew-ffmpeg"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        monkeypatch.setattr(ffmpeg_mod, "_MACOS_HOMEBREW_PATHS", (binary,))
        assert find_ffmpeg() == binary.resolve()

    def test_macos_homebrew_missing(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(ffmpeg_mod.sys, "platform", "darwin")
        monkeypatch.setattr(ffmpeg_mod, "_MACOS_HOMEBREW_PATHS", (base / "nope",))
        assert find_ffmpeg() is None

    def test_windows_local_exec(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.platform, "system", lambda: "Windows")
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        (base / "bin").mkdir()
        binary = base / "bin" / "ffmpeg.exe"
        binary.write_text("x")
        assert find_ffmpeg() == binary.resolve()


class TestBundledFfmpeg:
    def test_meipass_fallback(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        meipass = base / "meipass"
        meipass.mkdir()
        binary = meipass / "ffmpeg"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        monkeypatch.setattr(ffmpeg_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(ffmpeg_mod.sys, "_MEIPASS", str(meipass), raising=False)
        assert find_ffmpeg() == binary.resolve()

    def test_path_wins_over_meipass(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
        meipass = base / "meipass"
        meipass.mkdir()
        bundled = meipass / "ffmpeg"
        bundled.write_text("#!/bin/sh\n")
        bundled.chmod(0o755)
        monkeypatch.setattr(ffmpeg_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(ffmpeg_mod.sys, "_MEIPASS", str(meipass), raising=False)
        assert find_ffmpeg() == Path("/usr/bin/ffmpeg").resolve()

    def test_meipass_wins_over_bin_dir(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        meipass = base / "meipass"
        meipass.mkdir()
        bundled = meipass / "ffmpeg"
        bundled.write_text("#!/bin/sh\n")
        bundled.chmod(0o755)
        (base / "bin").mkdir()
        local = base / "bin" / "ffmpeg"
        local.write_text("#!/bin/sh\n")
        local.chmod(0o755)
        monkeypatch.setattr(ffmpeg_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(ffmpeg_mod.sys, "_MEIPASS", str(meipass), raising=False)
        assert find_ffmpeg() == bundled.resolve()

    def test_meipass_ignored_when_not_executable(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(ffmpeg_mod, "_MACOS_HOMEBREW_PATHS", ())
        monkeypatch.setattr(ffmpeg_mod.sys, "frozen", True, raising=False)
        monkeypatch.setattr(ffmpeg_mod.sys, "_MEIPASS", str(base), raising=False)
        (base / "ffmpeg").write_text("x")
        assert find_ffmpeg() is None


class TestInstallCoordination:
    def test_install_flag_toggles(self, monkeypatch, base):
        observed = []

        def impl(progress_cb=None, cancel_check=None):
            observed.append(install_in_progress())
            return base / "bin" / "ffmpeg"

        monkeypatch.setattr(ffmpeg_mod, "_download_and_install_impl", impl)
        result = download_and_install()
        assert result == base / "bin" / "ffmpeg"
        assert observed == [True]
        assert install_in_progress() is False

    def test_second_call_waits_for_first(self, monkeypatch, base):
        started = threading.Event()
        release = threading.Event()
        results = []

        def impl(progress_cb=None, cancel_check=None):
            started.set()
            release.wait(10)
            return base / "bin" / "ffmpeg"

        monkeypatch.setattr(ffmpeg_mod, "_download_and_install_impl", impl)
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: base / "bin" / "ffmpeg")

        def run():
            results.append(download_and_install())

        t = threading.Thread(target=run, daemon=True)
        t.start()
        assert started.wait(10)
        release.set()
        second = download_and_install()
        t.join(10)
        assert second == base / "bin" / "ffmpeg"
        assert results == [base / "bin" / "ffmpeg"]

    def test_install_event_set_on_failure(self, monkeypatch, base):
        def impl(progress_cb=None, cancel_check=None):
            raise FfmpegInstallError("boom")

        monkeypatch.setattr(ffmpeg_mod, "_download_and_install_impl", impl)
        with pytest.raises(FfmpegInstallError):
            download_and_install()
        assert install_in_progress() is False


class TestClaimInstall:
    def test_claim_has_single_owner(self):
        try:
            assert ffmpeg_mod.claim_install() is True
            assert ffmpeg_mod.claim_install() is False
            assert ffmpeg_mod.install_in_progress() is True
        finally:
            ffmpeg_mod._install_event.set()
            with ffmpeg_mod._install_lock:
                ffmpeg_mod._install_in_progress = False

    def test_run_install_releases_claim(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod, "_download_and_install_impl", lambda *a, **k: base / "bin" / "ffmpeg")
        assert ffmpeg_mod.claim_install() is True
        result = ffmpeg_mod.run_install()
        assert result == base / "bin" / "ffmpeg"
        assert ffmpeg_mod.install_in_progress() is False
        assert ffmpeg_mod._install_event.is_set()


class TestWaitUntilReady:
    def test_ready_returns_immediately(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))
        assert wait_until_ready() is True

    def test_not_installing_returns_false(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: None)
        monkeypatch.setattr(ffmpeg_mod, "_install_in_progress", False)
        assert wait_until_ready(timeout=0.1) is False

    def test_waits_for_ongoing_install(self, monkeypatch):
        state = {"ready": False}
        event = threading.Event()
        monkeypatch.setattr(ffmpeg_mod, "_install_in_progress", True)
        monkeypatch.setattr(ffmpeg_mod, "_install_event", event)
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg") if state["ready"] else None)

        def finish():
            time.sleep(0.05)
            state["ready"] = True
            event.set()

        threading.Thread(target=finish, daemon=True).start()
        assert wait_until_ready(timeout=10) is True

    def test_waits_but_still_missing(self, monkeypatch):
        event = threading.Event()
        monkeypatch.setattr(ffmpeg_mod, "_install_in_progress", True)
        monkeypatch.setattr(ffmpeg_mod, "_install_event", event)
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: None)

        def finish():
            time.sleep(0.05)
            event.set()

        threading.Thread(target=finish, daemon=True).start()
        assert wait_until_ready(timeout=10) is False


class TestIsReady:
    def test_true_when_found(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))
        assert ffmpeg_mod.is_ready() is True

    def test_false_when_missing(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: None)
        assert ffmpeg_mod.is_ready() is False


class TestFfmpegDir:
    def test_returns_parent(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: "/opt/ffmpeg/bin/ffmpeg")
        assert ffmpeg_dir() == Path("/opt/ffmpeg/bin")

    def test_none_when_missing(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(ffmpeg_mod, "_MACOS_HOMEBREW_PATHS", ())
        assert ffmpeg_dir() is None


class TestResolveDownloadUrl:
    def test_static_url_passthrough(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: "https://x/y.zip")
        assert _resolve_download_url() == "https://x/y.zip"

    def test_evermeet_json(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: EVERMEET_INFO_URL)
        payload = json.dumps({"download": {"zip": {"url": "https://evermeet.cx/ffmpeg/ffmpeg-8.1.2.zip"}}}).encode()
        monkeypatch.setattr(ffmpeg_mod, "_http_get", lambda *a, **k: payload)
        assert _resolve_download_url() == "https://evermeet.cx/ffmpeg/ffmpeg-8.1.2.zip"

    def test_evermeet_http_failure(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: EVERMEET_INFO_URL)
        monkeypatch.setattr(ffmpeg_mod, "_http_get", lambda *a, **k: None)
        with pytest.raises(FfmpegInstallError):
            _resolve_download_url()

    def test_evermeet_bad_json(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: EVERMEET_INFO_URL)
        monkeypatch.setattr(ffmpeg_mod, "_http_get", lambda *a, **k: b"not json")
        with pytest.raises(FfmpegInstallError):
            _resolve_download_url()

    def test_unsupported_none(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: None)
        assert _resolve_download_url() is None


class TestHttpGet:
    def test_returns_bytes(self, monkeypatch):
        monkeypatch.setattr(
            ffmpeg_mod.urllib.request,
            "urlopen",
            lambda req, timeout=30, **kw: FakeResponse(b"hello"),
        )
        assert _http_get("https://x") == b"hello"

    def test_error_returns_none(self, monkeypatch):
        def boom(req, timeout=30, **kw):
            raise OSError("net down")

        monkeypatch.setattr(ffmpeg_mod.urllib.request, "urlopen", boom)
        assert _http_get("https://x") is None

    def test_cancel_raises(self):
        with pytest.raises(FfmpegInstallError):
            _http_get("https://x", cancel_check=lambda: True)


class TestDownload:
    def test_writes_file_and_progress(self, monkeypatch, tmp_path):
        data = b"x" * 200_000
        monkeypatch.setattr(
            ffmpeg_mod.urllib.request,
            "urlopen",
            lambda req, timeout=60, **kw: FakeResponse(data, len(data)),
        )
        dest = tmp_path / "ffmpeg-test.zip"
        calls = []
        _download("https://x/ffmpeg-test.zip", dest, lambda p, s, e: calls.append((p, s, e)), None)
        assert dest.read_bytes() == data
        assert calls
        assert calls[-1][0] > 99.0

    def test_cancel_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            ffmpeg_mod.urllib.request,
            "urlopen",
            lambda req, timeout=60, **kw: FakeResponse(b"x" * 1000, 1000),
        )
        with pytest.raises(FfmpegInstallError):
            _download("https://x/y.zip", tmp_path / "y.zip", None, lambda: True)

    def test_network_error_raises(self, monkeypatch, tmp_path):
        def boom(req, timeout=60, **kw):
            raise OSError("down")

        monkeypatch.setattr(ffmpeg_mod.urllib.request, "urlopen", boom)
        with pytest.raises(FfmpegInstallError):
            _download("https://x/y.zip", tmp_path / "y.zip", None, None)


class TestExtract:
    def test_zip(self, tmp_path):
        archive = tmp_path / "a.zip"
        archive.write_bytes(_make_zip({"bin/ffmpeg": b"x", "bin/ffprobe": b"y", "README": b"z"}))
        out = tmp_path / "out"
        _extract(archive, out)
        assert (out / "bin" / "ffmpeg").read_bytes() == b"x"
        assert (out / "bin" / "ffprobe").read_bytes() == b"y"

    def test_tar_xz(self, tmp_path):
        archive = tmp_path / "a.tar.xz"
        archive.write_bytes(_make_tar_xz({"ffmpeg": b"x", "ffprobe": b"y"}))
        out = tmp_path / "out"
        _extract(archive, out)
        assert (out / "ffmpeg").read_bytes() == b"x"

    def test_zip_with_directory_entries(self, tmp_path):
        archive = tmp_path / "d.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("bin/", "")
            zf.writestr("bin/ffmpeg", b"x")
        archive.write_bytes(buf.getvalue())
        out = tmp_path / "out"
        _extract(archive, out)
        assert (out / "bin").is_dir()
        assert (out / "bin" / "ffmpeg").read_bytes() == b"x"

    def test_tar_with_dir_and_symlink_members(self, tmp_path):
        archive = tmp_path / "d.tar.xz"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:xz") as tf:
            dir_info = tarfile.TarInfo("sub/")
            dir_info.type = tarfile.DIRTYPE
            tf.addfile(dir_info)
            link_info = tarfile.TarInfo("sub/link")
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = "ffmpeg"
            tf.addfile(link_info)
            data = tarfile.TarInfo("sub/ffmpeg")
            data.size = 3
            tf.addfile(data, io.BytesIO(b"abc"))
        archive.write_bytes(buf.getvalue())
        out = tmp_path / "out"
        _extract(archive, out)
        assert (out / "sub").is_dir()
        assert (out / "sub" / "ffmpeg").read_bytes() == b"abc"
        assert not (out / "sub" / "link").exists()

    def test_tar_extractfile_none_skipped(self, tmp_path, monkeypatch):
        archive = tmp_path / "e.tar.xz"
        archive.write_bytes(_make_tar_xz({"ffmpeg": b"abc"}))

        real_extractfile = tarfile.TarFile.extractfile

        def fake_extractfile(self, member, *args, **kwargs):
            if member.name == "ffmpeg":
                return None
            return real_extractfile(self, member, *args, **kwargs)

        monkeypatch.setattr(tarfile.TarFile, "extractfile", fake_extractfile)
        out = tmp_path / "out"
        _extract(archive, out)
        assert not (out / "ffmpeg").exists()

    def test_unsupported_extension(self, tmp_path):
        archive = tmp_path / "a.bin"
        archive.write_bytes(b"x")
        with pytest.raises(FfmpegInstallError):
            _extract(archive, tmp_path / "out")

    def test_zip_traversal_rejected(self, tmp_path):
        archive = tmp_path / "a.zip"
        archive.write_bytes(_make_zip({"../evil.txt": b"x"}))
        with pytest.raises(FfmpegInstallError):
            _extract(archive, tmp_path / "out")


class TestFindBinaries:
    def test_nested(self, tmp_path):
        (tmp_path / "pkg" / "bin").mkdir(parents=True)
        (tmp_path / "pkg" / "bin" / "ffmpeg.exe").write_text("a")
        (tmp_path / "pkg" / "bin" / "ffprobe.exe").write_text("b")
        found = _find_binaries(tmp_path)
        assert set(found) == {"ffmpeg", "ffprobe"}
        assert found["ffmpeg"].name == "ffmpeg.exe"

    def test_missing(self, tmp_path):
        (tmp_path / "x.txt").write_text("a")
        assert _find_binaries(tmp_path) == {}


class TestDownloadAndInstall:
    def test_install_success(self, monkeypatch, base):
        zip_bytes = _make_zip({"pkg/bin/ffmpeg": b"ffmpeg-binary", "pkg/bin/ffprobe": b"ffprobe-binary"})
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: "https://example.com/ffmpeg-test.zip")
        monkeypatch.setattr(
            ffmpeg_mod.urllib.request,
            "urlopen",
            lambda req, timeout=60, **kw: FakeResponse(zip_bytes, len(zip_bytes)),
        )
        monkeypatch.setattr(ffmpeg_mod, "_smoke_test", lambda target: None)
        path = download_and_install()
        assert path == base / "bin" / "ffmpeg"
        assert (base / "bin" / "ffmpeg").read_bytes() == b"ffmpeg-binary"
        assert (base / "bin" / "ffprobe").read_bytes() == b"ffprobe-binary"
        assert list((base / "bin").glob(".ffmpeg-download-*")) == []

    def test_unsupported_platform_returns_none(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: None)
        assert download_and_install() is None

    def test_missing_ffmpeg_in_archive(self, monkeypatch, base):
        zip_bytes = _make_zip({"readme.txt": b"hi"})
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: "https://example.com/ffmpeg-test.zip")
        monkeypatch.setattr(
            ffmpeg_mod.urllib.request,
            "urlopen",
            lambda req, timeout=60, **kw: FakeResponse(zip_bytes, len(zip_bytes)),
        )
        with pytest.raises(FfmpegInstallError):
            download_and_install()

    def test_cancel_raises(self, monkeypatch, base):
        monkeypatch.setattr(ffmpeg_mod, "get_download_url", lambda: "https://example.com/ffmpeg-test.zip")
        monkeypatch.setattr(
            ffmpeg_mod.urllib.request,
            "urlopen",
            lambda req, timeout=60, **kw: FakeResponse(b"x", 10),
        )
        with pytest.raises(FfmpegInstallError):
            download_and_install(cancel_check=lambda: True)

    def test_unexpected_error_wrapped(self, monkeypatch, base):
        def boom():
            raise ValueError("boom")

        monkeypatch.setattr(ffmpeg_mod, "get_download_url", boom)
        with pytest.raises(FfmpegInstallError):
            download_and_install()


class TestGetFfmpegVersion:
    def test_none_when_missing(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: None)
        assert get_ffmpeg_version() is None

    def test_parses_version(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))

        class FakeProc:
            returncode = 0
            stdout = "ffmpeg version 6.1.1-static Copyright (c) 2000-2023 the FFmpeg developers\n..."

        monkeypatch.setattr(ffmpeg_mod.subprocess, "run", lambda *a, **k: FakeProc())
        assert get_ffmpeg_version() == "6.1.1"

    def test_parses_n_prefixed_version(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))

        class FakeProc:
            returncode = 0
            stdout = "ffmpeg version n8.1.2 Copyright (c) 2000-2026 the FFmpeg developers\n..."

        monkeypatch.setattr(ffmpeg_mod.subprocess, "run", lambda *a, **k: FakeProc())
        assert get_ffmpeg_version() == "8.1.2"

    def test_nonzero_returncode(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))

        class FakeProc:
            returncode = 1
            stdout = ""

        monkeypatch.setattr(ffmpeg_mod.subprocess, "run", lambda *a, **k: FakeProc())
        assert get_ffmpeg_version() is None

    def test_returns_first_line_without_version_number(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))

        class FakeProc:
            returncode = 0
            stdout = "ffmpeg (custom build)\nsecond line\n"

        monkeypatch.setattr(ffmpeg_mod.subprocess, "run", lambda *a, **k: FakeProc())
        assert get_ffmpeg_version() == "ffmpeg (custom build)"

    def test_subprocess_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_mod, "find_ffmpeg", lambda: Path("/usr/bin/ffmpeg"))

        def boom(*a, **k):
            raise OSError("spawn failed")

        monkeypatch.setattr(ffmpeg_mod.subprocess, "run", boom)
        assert get_ffmpeg_version() is None


class TestSmokeTest:
    def test_failure_raises(self, tmp_path):
        binary = tmp_path / "ffmpeg"
        binary.write_text("not an executable")
        binary.chmod(0o755)
        with pytest.raises(FfmpegInstallError):
            _smoke_test(tmp_path)
