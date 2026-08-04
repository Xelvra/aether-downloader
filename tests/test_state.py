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

    def test_out_of_range_crf_coerced(self):
        state = AppState({})
        state.update_config_from_ui(
            quality="Nejlepší dostupná",
            fmt="Video + audio (MP4)",
            output_folder="/tmp/out",
            cookies_source="Žádný (Bez cookies)",
            cookies_file_path="",
            re_encode=True,
            crf="100",
            preset="fast",
        )
        assert state.config["crf"] == 23

    def test_repeated_updates_accumulate(self):
        state = AppState({})
        state.update_config_from_ui("720p", "Video + audio (MP4)", "/tmp/out", "Chrome", "")
        state.update_config_from_ui(
            "1080p",
            "Pouze zvuk (MP3)",
            "/tmp/out2",
            "Firefox",
            "/path/cookies.txt",
            re_encode=True,
            crf="20",
            preset="slow",
        )
        assert state.config["quality"] == "1080p"
        assert state.config["format"] == "Pouze zvuk (MP3)"
        assert state.config["output_folder"] == "/tmp/out2"
        assert state.config["cookies_source"] == "Firefox"
        assert state.config["re_encode"] is True
        assert state.config["crf"] == 20
        assert state.config["preset"] == "slow"

    def test_unknown_existing_keys_preserved(self):
        state = AppState({"custom_flag": "keep"})
        state.update_config_from_ui("720p", "Video + audio (MP4)", "/tmp/out", "Žádný (Bez cookies)", "")
        assert state.config["custom_flag"] == "keep"
