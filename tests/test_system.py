import sys

import stahovac.utils.system as sys_mod
from stahovac.utils.system import open_folder_in_explorer, open_path


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
        monkeypatch.setattr(sys_mod, "_run_startfile", lambda p: (called.append(p) or (True, "")))
        ok, message = open_path(str(tmp_path))
        assert ok is True
        assert message == ""
        assert called == [str(tmp_path.resolve())]

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


class TestOpenFolderInExplorer:
    def test_nonexistent_path(self):
        assert open_folder_in_explorer("/nonexistent/path/12345") is False

    def test_existent_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(sys_mod, "_run", lambda cmd, timeout=10: (True, ""))
        assert open_folder_in_explorer(str(tmp_path)) is True

    def test_existent_path_resolves_relative(self, monkeypatch):
        monkeypatch.setattr(sys_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(sys_mod, "_run", lambda cmd, timeout=10: (True, ""))
        assert open_folder_in_explorer(".") is True
