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


def _make_app():
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
    return app, statuses


class TestCrfValidationGating:
    def test_empty_crf_allowed_without_reencode(self):
        app, statuses = _make_app()
        app.quality_view = _QualityView(whole_video=False, re_encode=False, crf="")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        assert app.started, "stahování mělo začít i bez CRF"
        assert not any("CRF" in text for text, _ in statuses)
        assert app.started[0].crf == 23

    def test_empty_crf_blocked_with_reencode(self):
        app, statuses = _make_app()
        app.quality_view = _QualityView(whole_video=False, re_encode=True, crf="")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        assert app.started == []
        assert any("CRF" in text for text, _ in statuses)
        assert app._unlock_count["n"] == 1

    def test_valid_crf_with_reencode(self):
        app, statuses = _make_app()
        app.quality_view = _QualityView(whole_video=False, re_encode=True, crf="20")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        assert app.started and app.started[0].crf == 20

    def test_whole_video_skips_crf_validation(self):
        app, statuses = _make_app()
        app.quality_view = _QualityView(whole_video=True, crf="")
        app._start_download_impl("https://www.youtube.com/watch?v=abc")
        assert app.started
