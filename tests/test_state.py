from stahovac.state import AppState


class TestAppState:
    def test_update_config_from_ui(self):
        state = AppState({})
        state.update_config_from_ui(
            quality="720p",
            fmt="Video + audio (MP4)",
            output_folder="/tmp/out",
            cookies_source="Chrome",
            cookies_file_path="",
        )
        assert state.config["quality"] == "720p"
        assert state.config["format"] == "Video + audio (MP4)"
        assert state.config["output_folder"] == "/tmp/out"
        assert state.config["cookies_source"] == "Chrome"
        assert state.config["re_encode"] is False
        assert state.config["crf"] == 23
        assert state.config["preset"] == "fast"

    def test_update_config_from_ui_custom_trim(self):
        state = AppState({})
        state.update_config_from_ui(
            quality="Nejlepší dostupná",
            fmt="Pouze zvuk (MP3)",
            output_folder="/tmp/out",
            cookies_source="Žádný (Bez cookies)",
            cookies_file_path="/path/cookies.txt",
            re_encode=True,
            crf="18",
            preset="slow",
        )
        assert state.config["re_encode"] is True
        assert state.config["crf"] == 18
        assert state.config["preset"] == "slow"

    def test_invalid_crf_and_preset_coerced(self):
        state = AppState({})
        state.update_config_from_ui(
            quality="Nejlepší dostupná",
            fmt="Video + audio (MP4)",
            output_folder="/tmp/out",
            cookies_source="Žádný (Bez cookies)",
            cookies_file_path="",
            re_encode=True,
            crf="abc",
            preset="nonexistent",
        )
        assert state.config["crf"] == 23
        assert state.config["preset"] == "fast"

    def test_initial_state(self):
        state = AppState({"quality": "1080p"})
        assert state.config["quality"] == "1080p"
        assert not hasattr(state, "is_downloading")
