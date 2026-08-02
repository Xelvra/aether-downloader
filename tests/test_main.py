import os
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

    def test_check_flags(self, monkeypatch):
        monkeypatch.delenv("AETHER_CHECK_URL", raising=False)
        monkeypatch.delenv("AETHER_CHECK_OUTPUT", raising=False)
        args = main_mod.parse_args(["--check", "--check-url", "https://example.com/v", "--check-output", "out.json"])
        assert args.check is True
        assert args.check_url == "https://example.com/v"
        assert args.check_output == "out.json"

    def test_check_flags_from_env(self, monkeypatch):
        monkeypatch.setenv("AETHER_CHECK_URL", "https://env.example/v")
        monkeypatch.setenv("AETHER_CHECK_OUTPUT", "env.json")
        args = main_mod.parse_args(["--check"])
        assert args.check_url == "https://env.example/v"
        assert args.check_output == "env.json"


class TestConfigureSsl:
    def test_sets_ca_env_vars_when_bundle_exists(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
        cafile = tmp_path / "cacert.pem"
        cafile.write_text("dummy")
        import certifi

        monkeypatch.setattr(certifi, "where", lambda: str(cafile))
        main_mod._configure_ssl()
        assert os.environ["SSL_CERT_FILE"] == str(cafile)
        assert os.environ["CURL_CA_BUNDLE"] == str(cafile)

    def test_skips_when_env_already_set(self, monkeypatch):
        monkeypatch.setenv("SSL_CERT_FILE", "/custom/ca.pem")
        monkeypatch.setenv("CURL_CA_BUNDLE", "/custom/curl.pem")
        main_mod._configure_ssl()
        assert os.environ["SSL_CERT_FILE"] == "/custom/ca.pem"
        assert os.environ["CURL_CA_BUNDLE"] == "/custom/curl.pem"

    def test_does_not_set_when_bundle_missing(self, monkeypatch):
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
        import certifi

        monkeypatch.setattr(certifi, "where", lambda: "/nonexistent/cacert.pem")
        main_mod._configure_ssl()
        assert "SSL_CERT_FILE" not in os.environ
        assert "CURL_CA_BUNDLE" not in os.environ
