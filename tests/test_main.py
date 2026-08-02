import sys

import stahovac.__main__ as main_mod


class TestIsHeadless:
    def test_windows_never_headless(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert main_mod._is_headless() is False

    def test_macos_never_headless(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert main_mod._is_headless() is False

    def test_linux_with_display(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert main_mod._is_headless() is False

    def test_linux_with_wayland(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert main_mod._is_headless() is False

    def test_linux_without_display(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert main_mod._is_headless() is True


class TestParseArgs:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("AETHER_HOST", raising=False)
        monkeypatch.delenv("AETHER_PORT", raising=False)
        args = main_mod.parse_args([])
        assert args.host == "127.0.0.1"
        assert args.port == 8000
        assert args.web is False

    def test_web_flag(self):
        args = main_mod.parse_args(["--web"])
        assert args.web is True

    def test_host_port(self):
        args = main_mod.parse_args(["--host", "0.0.0.0", "--port", "9000"])
        assert args.host == "0.0.0.0"
        assert args.port == 9000

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("AETHER_HOST", "10.0.0.1")
        monkeypatch.setenv("AETHER_PORT", "5555")
        args = main_mod.parse_args([])
        assert args.host == "10.0.0.1"
        assert args.port == 5555
