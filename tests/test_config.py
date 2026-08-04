import json
from pathlib import Path

import pytest

from stahovac.config.app_config import migrate
from stahovac.config.constants import (
    CONFIG_FILE_NAME,
    COOKIES_NONE,
    DOWNLOADS_DIR_NAME,
    FORMAT_MP4,
    QUALITY_BEST,
    MediaFormat,
)
from stahovac.config.manager import ConfigManager
from stahovac.utils.paths import set_base_dir


@pytest.fixture(autouse=True)
def temp_config_dir(tmp_path):
    set_base_dir(tmp_path)
    return tmp_path


class TestConfigMigrations:
    def test_migrate_v1_format_tokens_to_labels(self):
        out = migrate({"quality": "1080p", "format": "mp3", "schema_version": 1})
        assert out["format"] == MediaFormat.MP3.value
        assert out["schema_version"] == 2
        assert out["re_encode"] is False
        assert out["crf"] == 23
        assert out["preset"] == "fast"

    def test_migrate_all_v1_tokens(self):
        assert migrate({"format": "mp4"})["format"] == MediaFormat.MP4.value
        assert migrate({"format": "srt"})["format"] == MediaFormat.SUBS.value

    def test_migrate_current_schema_passthrough(self):
        raw = {"schema_version": 2, "format": FORMAT_MP4}
        out = migrate(raw)
        assert out["schema_version"] == 2
        assert out["format"] == FORMAT_MP4

    def test_migrate_missing_version_defaults_to_v1(self):
        out = migrate({"format": "srt"})
        assert out["schema_version"] == 2
        assert out["format"] == MediaFormat.SUBS.value

    def test_load_migrates_v1_config_and_persists(self, temp_config_dir):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        config_path.write_text(json.dumps({"quality": "1080p", "format": "mp3", "schema_version": 1}), encoding="utf-8")
        cfg = ConfigManager.load()
        assert cfg["format"] == MediaFormat.MP3.value
        assert cfg["schema_version"] == 2
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["schema_version"] == 2
        assert saved["format"] == MediaFormat.MP3.value


class TestConfigManager:
    def test_get_default_config(self, temp_config_dir):
        cfg = ConfigManager.get_default_config()
        assert cfg["quality"] == QUALITY_BEST
        assert cfg["format"] == FORMAT_MP4
        assert cfg["cookies_source"] == COOKIES_NONE
        assert cfg["cookies_file_path"] == ""
        assert cfg["re_encode"] is False
        assert cfg["crf"] == 23
        assert cfg["preset"] == "fast"
        assert cfg["schema_version"] == 2
        downloads_dir = temp_config_dir / DOWNLOADS_DIR_NAME
        assert cfg["output_folder"] == str(downloads_dir)

    def test_load_returns_default_when_no_config(self, temp_config_dir):
        cfg = ConfigManager.load()
        assert cfg["quality"] == QUALITY_BEST

    def test_save_and_load(self, temp_config_dir):
        test_cfg = {
            "quality": "720p",
            "format": FORMAT_MP4,
            "output_folder": str(temp_config_dir),
            "cookies_source": COOKIES_NONE,
            "cookies_file_path": "",
            "re_encode": False,
            "crf": 23,
            "preset": "fast",
            "schema_version": 2,
        }
        result = ConfigManager.save(test_cfg)
        assert result is True

        config_path = temp_config_dir / CONFIG_FILE_NAME
        assert config_path.exists()

        loaded = ConfigManager.load()
        assert loaded["quality"] == "720p"

    def test_load_handles_corrupted_json(self, temp_config_dir):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        config_path.write_text("not valid json", encoding="utf-8")
        cfg = ConfigManager.load()
        assert cfg["quality"] == QUALITY_BEST

    def test_load_adds_missing_keys(self, temp_config_dir):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        partial = {"quality": "1080p"}
        config_path.write_text(json.dumps(partial), encoding="utf-8")

        cfg = ConfigManager.load()
        assert cfg["quality"] == "1080p"
        assert cfg["format"] == FORMAT_MP4
        assert cfg["cookies_source"] == COOKIES_NONE
        assert cfg["re_encode"] is False
        assert cfg["crf"] == 23
        assert cfg["preset"] == "fast"

    def test_save_failure_returns_false(self, temp_config_dir):
        result = ConfigManager.save({})
        assert result is True

    def test_load_fixes_missing_output_folder(self, temp_config_dir):
        missing = str(temp_config_dir / "nonexistent")
        config_path = temp_config_dir / CONFIG_FILE_NAME
        data = {
            "quality": QUALITY_BEST,
            "format": FORMAT_MP4,
            "output_folder": missing,
            "cookies_source": COOKIES_NONE,
            "cookies_file_path": "",
        }
        config_path.write_text(json.dumps(data), encoding="utf-8")

        cfg = ConfigManager.load()
        assert cfg["output_folder"] == str(temp_config_dir / DOWNLOADS_DIR_NAME)

    def test_load_fixes_invalid_types(self, temp_config_dir):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        data = {
            "quality": 123,
            "format": None,
            "output_folder": str(temp_config_dir),
            "cookies_source": "Nesmysl",
            "cookies_file_path": 42,
            "re_encode": "ano",
            "crf": [],
            "preset": 123,
        }
        config_path.write_text(json.dumps(data), encoding="utf-8")

        cfg = ConfigManager.load()
        assert cfg["quality"] == QUALITY_BEST
        assert cfg["format"] == FORMAT_MP4
        assert cfg["cookies_source"] == COOKIES_NONE
        assert cfg["cookies_file_path"] == ""
        assert cfg["re_encode"] is True
        assert cfg["crf"] == 23
        assert cfg["preset"] == "fast"

    def test_load_does_not_crash_on_uncreatable_output_folder(self, temp_config_dir, monkeypatch):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        config_path.write_text(
            json.dumps(
                {
                    "quality": QUALITY_BEST,
                    "format": FORMAT_MP4,
                    "output_folder": str(temp_config_dir / "nope"),
                    "cookies_source": COOKIES_NONE,
                }
            ),
            encoding="utf-8",
        )

        def fake_mkdir(*a, **k):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "mkdir", fake_mkdir)
        cfg = ConfigManager.load()
        assert cfg["quality"] == QUALITY_BEST

    def test_ensure_output_folder_tolerates_errors(self, monkeypatch):
        def fake_mkdir(*a, **k):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "mkdir", fake_mkdir)
        ConfigManager._ensure_output_folder("/uncreatable/path")

    def test_ensure_output_folder_empty_is_noop(self):
        ConfigManager._ensure_output_folder("")

    def test_load_handles_non_dict_json(self, temp_config_dir):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        config_path.write_text("[1, 2, 3]", encoding="utf-8")
        cfg = ConfigManager.load()
        assert cfg["quality"] == QUALITY_BEST

    def test_save_fsync_failure_returns_false(self, temp_config_dir, monkeypatch):
        import os

        config_path = temp_config_dir / CONFIG_FILE_NAME

        def fake_fsync(fd):
            raise OSError("disk full")

        monkeypatch.setattr(os, "fsync", fake_fsync)
        assert ConfigManager.save({"quality": "1080p"}) is False
        assert not config_path.exists()

    def test_load_fixes_none_value(self, temp_config_dir):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        data = {
            "quality": QUALITY_BEST,
            "format": FORMAT_MP4,
            "output_folder": str(temp_config_dir),
            "cookies_source": COOKIES_NONE,
            "cookies_file_path": "",
            "re_encode": False,
            "crf": None,
            "preset": "fast",
        }
        config_path.write_text(json.dumps(data), encoding="utf-8")
        cfg = ConfigManager.load()
        assert cfg["crf"] == 23
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["crf"] == 23

    def test_load_fixes_list_value(self, temp_config_dir):
        config_path = temp_config_dir / CONFIG_FILE_NAME
        data = {
            "quality": QUALITY_BEST,
            "format": FORMAT_MP4,
            "output_folder": str(temp_config_dir),
            "cookies_source": COOKIES_NONE,
            "cookies_file_path": "",
            "re_encode": False,
            "crf": [1, 2, 3],
            "preset": "fast",
        }
        config_path.write_text(json.dumps(data), encoding="utf-8")
        cfg = ConfigManager.load()
        assert cfg["crf"] == 23


class TestRawVersion:
    def test_invalid_schema_version_defaults_to_v1(self):
        out = migrate({"schema_version": "abc", "format": "mp3"})
        assert out["schema_version"] == 2
        assert out["format"] == MediaFormat.MP3.value


class TestAppConfigCoercion:
    def test_post_init_invalid_preset_resets(self):
        from stahovac.config.app_config import AppConfig

        assert AppConfig(preset="bogus").preset == "fast"

    def test_post_init_empty_quality_resets(self):
        from stahovac.config.app_config import AppConfig

        assert AppConfig(quality="").quality == QUALITY_BEST

    def test_post_init_empty_format_resets(self):
        from stahovac.config.app_config import AppConfig

        assert AppConfig(format="").format == FORMAT_MP4

    def test_coerce_bool_int(self):
        from stahovac.config.app_config import _coerce_bool

        assert _coerce_bool(1) is True
        assert _coerce_bool(0) is False

    def test_coerce_bool_random_string_false(self):
        from stahovac.config.app_config import _coerce_bool

        assert _coerce_bool("random") is False
        assert _coerce_bool(None) is False

    def test_coerce_crf_out_of_range(self):
        from stahovac.config.app_config import coerce_crf

        assert coerce_crf(100) == 23
        assert coerce_crf(-5) == 23
