import sys
from pathlib import Path

from stahovac.utils.paths import (
    get_base_dir,
    get_frozen_base_dir,
    migrate_bundle_data,
    set_base_dir,
)


class TestPaths:
    def test_set_and_get_base_dir(self):
        custom_path = Path("/tmp/test_aether")
        set_base_dir(custom_path)
        assert get_base_dir() == custom_path

    def test_get_base_dir_default(self):
        set_base_dir(None)
        path = get_base_dir()
        assert isinstance(path, Path)
        assert path.exists()


class TestFrozenBaseDir:
    def test_app_bundle_uses_application_support(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(
            sys, "executable", "/Applications/Aether Downloader.app/Contents/MacOS/stahovac"
        )
        expected = Path.home() / "Library" / "Application Support" / "AetherDownloader"
        assert get_frozen_base_dir() == expected

    def test_app_bundle_detected_via_suffix(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(sys, "executable", "/tmp/Foo.app/Contents/MacOS/stahovac")
        expected = Path.home() / "Library" / "Application Support" / "AetherDownloader"
        assert get_frozen_base_dir() == expected

    def test_plain_binary_uses_executable_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(sys, "executable", "/home/user/bin/stahovac")
        assert get_frozen_base_dir() == Path("/home/user/bin")

    def test_non_bundle_macos_binary_uses_executable_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(sys, "executable", "/opt/stahovac/stahovac")
        assert get_frozen_base_dir() == Path("/opt/stahovac")


class TestMigrateBundleData:
    def test_creates_target_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        target = tmp_path / "nested" / "dir"
        migrate_bundle_data(target)
        assert target.is_dir()

    def test_copies_files_from_bundle(self, tmp_path, monkeypatch):
        bundle = tmp_path / "app.app" / "Contents" / "MacOS"
        bundle.mkdir(parents=True)
        (bundle / "config.json").write_text("{}", encoding="utf-8")
        (bundle / "downloads").mkdir()
        (bundle / "downloads" / "video.mp4").write_bytes(b"x")

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(bundle / "stahovac"))

        target = tmp_path / "support" / "AetherDownloader"
        migrate_bundle_data(target)

        assert (target / "config.json").read_text(encoding="utf-8") == "{}"
        assert (target / "downloads" / "video.mp4").read_bytes() == b"x"

    def test_does_not_overwrite_existing_data(self, tmp_path, monkeypatch):
        bundle = tmp_path / "app.app" / "Contents" / "MacOS"
        bundle.mkdir(parents=True)
        (bundle / "config.json").write_text("{}", encoding="utf-8")

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(bundle / "stahovac"))

        target = tmp_path / "support" / "AetherDownloader"
        target.mkdir(parents=True)
        (target / "config.json").write_text('{"keep": true}', encoding="utf-8")

        migrate_bundle_data(target)
        assert (target / "config.json").read_text(encoding="utf-8") == '{"keep": true}'
