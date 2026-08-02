from stahovac.gui.download_view import DownloadView
from stahovac.gui.quality_view import QualityView


class _FakePage:
    def update(self):
        pass


class TestQualityViewToParams:
    def test_crf_int_from_config_does_not_crash(self):
        view = QualityView(_FakePage(), config={"crf": 23})
        view.crf_input.value = 23
        params = view.to_params()
        assert params["crf"] == "23"

    def test_crf_none_value(self):
        view = QualityView(_FakePage(), config={})
        view.crf_input.value = None
        params = view.to_params()
        assert params["crf"] == ""

    def test_times_are_stripped(self):
        view = QualityView(_FakePage(), config={})
        view.start_time_input.value = " 00:01:30 "
        view.end_time_input.value = " 00:02:00 "
        params = view.to_params()
        assert params["start_time"] == "00:01:30"
        assert params["end_time"] == "00:02:00"

    def test_crf_input_displays_string(self):
        view = QualityView(_FakePage(), config={"crf": 23})
        assert view.crf_input.value == "23"


class TestDownloadViewGetUrl:
    def _make_view(self):
        return DownloadView(
            _FakePage(),
            metadata_service=None,
            config={},
            on_start_download=lambda url: None,
            on_cancel_download=lambda: None,
        )

    def test_none_value_returns_empty(self):
        view = self._make_view()
        view.url_input.value = None
        assert view._get_url() == ""

    def test_string_is_stripped(self):
        view = self._make_view()
        view.url_input.value = "  https://youtu.be/abc  "
        assert view._get_url() == "https://youtu.be/abc"

    def test_refresh_after_close_does_not_crash(self):
        view = self._make_view()
        view.close()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()

    def test_refresh_ignores_invalid_url(self):
        view = self._make_view()
        view.url_input.value = "not a url"
        view.refresh_metadata()

    def test_close_is_idempotent(self):
        view = self._make_view()
        view.close()
        view.close()
