from stahovac.gui.app import GuiApp


class _Value:
    def __init__(self, value):
        self.value = value


class _StorageView:
    def __init__(self):
        self.output_folder_text = _Value("/tmp/out")


class _QualityView:
    def __init__(self, **overrides):
        self.params = {
            "whole_video": True,
            "start_time": "00:00",
            "end_time": "00:00",
            "end_option": "Do konce videa",
            "re_encode": False,
            "crf": "23",
            "preset": "fast",
            "quality": "Nejlepší dostupná",
            "format_choice": "Video + audio (MP4)",
        }
        self.params.update(overrides)

    def to_params(self):
        return self.params


class _Manager:
    def __init__(self, validate_result=None):
        self._validate_result = validate_result
        self.validate_calls = []

    def validate(self, params, *, crf_raw=None):
        self.validate_calls.append((params, crf_raw))
        return self._validate_result


def _make_app(validate_result=None):
    app = GuiApp.__new__(GuiApp)
    app._is_downloading = False
    app._safari_cookies_blocking = lambda url: False
    app.storage_view = _StorageView()
    statuses = []
    app.on_status = lambda text, color: statuses.append((text, color))
    app._unlock_count = {"n": 0}
    app._force_unlock_ui = lambda: app._unlock_count.__setitem__("n", app._unlock_count["n"] + 1)
    app.started = []
    app._do_start_download = lambda params: app.started.append(params)
    app._manager = _Manager(validate_result)
    return app, statuses


class TestValidationGating:
    def test_validation_error_blocks_download(self):
        app, statuses = _make_app(validate_result="⚠️ Chyba")
        app.quality_view = _QualityView(whole_video=False, re_encode=True, crf="")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        assert app.started == []
        assert any("Chyba" in text for text, _ in statuses)
        assert app._unlock_count["n"] == 1

    def test_valid_request_starts_download(self):
        app, statuses = _make_app()
        app.quality_view = _QualityView(whole_video=False, re_encode=True, crf="20")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        assert app.started and app.started[0].crf == 20
        assert not any("CRF" in text for text, _ in statuses)

    def test_passes_raw_crf_to_manager(self):
        app, _ = _make_app()
        app.quality_view = _QualityView(whole_video=False, re_encode=True, crf="20")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        params, crf_raw = app._manager.validate_calls[0]
        assert crf_raw == "20"
        assert params.crf == 20

    def test_whole_video_skips_validation_error(self):
        app, _ = _make_app()
        app.quality_view = _QualityView(whole_video=True, crf="")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        assert app.started

    def test_empty_url_blocked(self):
        app, statuses = _make_app()
        app.quality_view = _QualityView()
        app._start_download_impl("")
        assert app.started == []
        assert any("URL" in text for text, _ in statuses)
