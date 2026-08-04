import sys

import stahovac.utils.system as sys_mod
from stahovac.utils.system import open_path


class TestIsWine:
    def test_linux_never_wine(self, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")
        assert sys_mod._is_wine() is False

    def test_windows_with_wine_env_is_wine(self, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Windows")
        monkeypatch.setenv("WINEPREFIX", "/home/t/.wine")
        monkeypatch.delenv("WINELOADER", raising=False)
        monkeypatch.delenv("WINESERVER", raising=False)
        assert sys_mod._is_wine() is True

    def test_windows_without_markers_not_wine(self, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Windows")
        monkeypatch.delenv("WINELOADER", raising=False)
        monkeypatch.delenv("WINESERVER", raising=False)
        monkeypatch.delenv("WINEPREFIX", raising=False)
        monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
        assert sys_mod._is_wine() is False

    def test_windows_wine_in_executable_is_wine(self, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Windows")
        monkeypatch.delenv("WINELOADER", raising=False)
        monkeypatch.delenv("WINESERVER", raising=False)
        monkeypatch.delenv("WINEPREFIX", raising=False)
        monkeypatch.setattr(sys, "executable", "/usr/lib/wine/wine64/.../python.exe")
        assert sys_mod._is_wine() is True


class TestWineToUnix:
    def test_z_drive_to_root(self):
        assert sys_mod._wine_to_unix(r"Z:\home\pc\videos\x.mp4") == "/home/pc/videos/x.mp4"

    def test_z_drive_forward_slashes(self):
        assert sys_mod._wine_to_unix("Z:/home/pc/videos/x.mp4") == "/home/pc/videos/x.mp4"

    def test_c_drive_to_wineprefix(self, monkeypatch):
        monkeypatch.setenv("WINEPREFIX", "/tmp/prefix")
        assert (
            sys_mod._wine_to_unix(r"C:\Users\pc\Downloads\x.mp4")
            == "/tmp/prefix/dosdevices/c:/Users/pc/Downloads/x.mp4"
        )

    def test_c_drive_default_prefix(self, monkeypatch, tmp_path):
        monkeypatch.delenv("WINEPREFIX", raising=False)
        result = sys_mod._wine_to_unix(r"C:\foo\x.mp4")
        assert result.endswith("dosdevices/c:/foo/x.mp4")

    def test_native_path_unchanged(self):
        assert sys_mod._wine_to_unix("/home/pc/x.mp4") == "/home/pc/x.mp4"


class TestRun:
    def test_success(self):
        ok, message = sys_mod._run([sys.executable, "-c", "pass"])
        assert ok is True
        assert message == ""

    def test_failure_reports_stderr(self):
        ok, message = sys_mod._run([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
        assert ok is False
        assert "boom" in message

    def test_missing_command(self):
        ok, message = sys_mod._run(["definitely-not-a-real-command-xyz"])
        assert ok is False
        assert "nenalezen" in message.lower()

    def test_timeout_reports_error(self):
        ok, message = sys_mod._run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
        assert ok is False
        assert "Časový limit" in message


class TestRunStartfile:
    def test_success(self, monkeypatch):
        import os

        monkeypatch.setattr(os, "startfile", lambda p: None, raising=False)
        ok, message = sys_mod._run_startfile("/tmp/somewhere")
        assert ok is True
        assert message == ""

    def test_failure(self, monkeypatch):
        import os

        def boom(p):
            raise OSError("no handler")

        monkeypatch.setattr(os, "startfile", boom, raising=False)
        ok, message = sys_mod._run_startfile("/tmp/somewhere")
        assert ok is False
        assert "OSError" in message


class TestOpenPath:
    def test_nonexistent_path_returns_error(self):
        ok, message = open_path("/nonexistent/path/12345")
        assert ok is False
        assert "neexistuje" in message.lower()

    def test_invalid_path_returns_error(self):
        ok, message = open_path("\x00")
        assert ok is False

    def test_windows_startfile_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Windows")
        called = []
        monkeypatch.setattr(sys_mod, "_run_startfile", lambda p: called.append(p) or (True, ""))
        ok, message = open_path(str(tmp_path))
        assert ok is True
        assert message == ""
        assert called == [str(tmp_path.resolve())]

    def test_windows_wine_uses_linux_opener(self, tmp_path, monkeypatch):
        """Pod Wine se místo os.startfile použije Linux otevírač (unixová cesta)."""
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Windows")
        monkeypatch.setattr(sys_mod, "_is_wine", lambda: True)
        monkeypatch.setattr(sys_mod, "_wine_to_unix", lambda p: "/tmp/unix/" + p.split(":")[-1])
        opened = []
        monkeypatch.setattr(sys_mod, "_open_linux", lambda p: opened.append(p) or (True, ""))
        ok, _ = open_path(str(tmp_path))
        assert ok is True
        assert opened, "Linux otevírač se měl použít pod Wine"

    def test_macos_open_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(sys_mod, "_run", lambda cmd, timeout=10: (True, ""))
        ok, _ = open_path(str(tmp_path))
        assert ok is True

    def test_linux_fallback_when_xdg_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")
        calls = []

        def fake_run(cmd, timeout=10):
            calls.append(cmd)
            return (False, "není nastaven program") if cmd[0] == "xdg-open" else (True, "")

        monkeypatch.setattr(sys_mod, "_run", fake_run)
        ok, _ = open_path(str(tmp_path))
        assert ok is True
        assert calls[0][0] == "xdg-open"
        assert calls[-1][0] in ("gio", "kde-open5", "kde-open", "exo-open")

    def test_linux_all_openers_fail_reports_reason(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(sys_mod, "_run", lambda cmd, timeout=10: (False, "žádný program"))
        ok, message = open_path(str(tmp_path))
        assert ok is False
        assert message

    def test_linux_missing_opener_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")

        def fake_run(cmd, timeout=10):
            if cmd[0] in ("xdg-open", "gio"):
                return (False, f"Příkaz nenalezen: {cmd[0]}")
            return (True, "")

        monkeypatch.setattr(sys_mod, "_run", fake_run)
        ok, _ = open_path(str(tmp_path))
        assert ok is True


class TestRevealInFileManager:
    def test_nonexistent_path_returns_error(self):
        ok, message = sys_mod.reveal_in_file_manager("/nonexistent/path/12345")
        assert ok is False
        assert "neexistuje" in message.lower()

    def test_invalid_path_returns_error(self):
        ok, message = sys_mod.reveal_in_file_manager("\x00")
        assert ok is False

    def test_windows_explorer_select(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Windows")
        called = []
        monkeypatch.setattr(sys_mod.subprocess, "Popen", lambda cmd, start_new_session=False: called.append(cmd))
        ok, message = sys_mod.reveal_in_file_manager(str(tmp_path))
        assert ok is True
        assert message == ""
        assert called == [["explorer", f"/select,{tmp_path.resolve()}"]]

    def test_windows_wine_uses_linux_reveal(self, tmp_path, monkeypatch):
        """Pod Wine se místo explorer /select použije Linux správce souborů."""
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Windows")
        monkeypatch.setattr(sys_mod, "_is_wine", lambda: True)
        monkeypatch.setattr(sys_mod, "_wine_to_unix", lambda p: "/tmp/unix/" + p.split(":")[-1])
        revealed = []
        monkeypatch.setattr(sys_mod, "_reveal_linux", lambda p: revealed.append(p) or (True, ""))
        ok, _ = sys_mod.reveal_in_file_manager(str(tmp_path))
        assert ok is True
        assert revealed, "Linux správce souborů se měl použít pod Wine"

    def test_macos_open_reveal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(sys_mod, "_run", lambda cmd, timeout=10: (True, ""))
        ok, _ = sys_mod.reveal_in_file_manager(str(tmp_path))
        assert ok is True

    def test_linux_selects_file_with_nautilus(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")
        calls = []

        def fake_run(cmd, timeout=10):
            calls.append(cmd)
            return (True, "") if cmd[0] == "nautilus" else (False, "žádný program")

        monkeypatch.setattr(sys_mod, "_run", fake_run)
        ok, _ = sys_mod.reveal_in_file_manager(str(tmp_path))
        assert ok is True
        assert calls[0] == ["nautilus", "--select", str(tmp_path.resolve())]

    def test_linux_missing_managers_falls_back_to_parent_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")
        calls = []

        def fake_run(cmd, timeout=10):
            calls.append(cmd)
            return (False, f"Příkaz nenalezen: {cmd[0]}")

        def fake_open_linux(path):
            calls.append(["xdg-open", path])
            return (True, "")

        monkeypatch.setattr(sys_mod, "_run", fake_run)
        monkeypatch.setattr(sys_mod, "_open_linux", fake_open_linux)
        ok, _ = sys_mod.reveal_in_file_manager(str(tmp_path))
        assert ok is True
        assert calls[-1] == ["xdg-open", str(tmp_path.parent.resolve())]

    def test_linux_select_failure_falls_back_to_parent_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")

        def fake_run(cmd, timeout=10):
            return (False, "nešlo vybrat")

        monkeypatch.setattr(sys_mod, "_run", fake_run)
        monkeypatch.setattr(sys_mod, "_open_linux", lambda path: (True, ""))
        ok, _ = sys_mod.reveal_in_file_manager(str(tmp_path))
        assert ok is True
