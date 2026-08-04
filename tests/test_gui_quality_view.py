import flet as ft

import stahovac.gui.theme as th
from stahovac.config.constants import END_OPTION_END, END_OPTION_FULL, FORMAT_MP4, QUALITY_BEST
from stahovac.gui.quality_view import QualityView


class _FakePage:
    def __init__(self):
        self.updates = 0

    def update(self):
        self.updates += 1


def _make(config=None, on_save=None):
    saved = []
    page = _FakePage()
    view = QualityView(page, config=config, on_save_callback=on_save or (lambda: saved.append(1)))
    return view, page, saved


class TestEndOptionChange:
    def test_do_konce_disables_end_time(self):
        view, page, _ = _make()
        view.end_option_radio.value = END_OPTION_FULL
        view._handle_end_option_change(None)
        assert view.end_time_input.disabled is True
        assert page.updates == 1

    def test_do_času_enables_end_time(self):
        view, page, _ = _make()
        view.end_option_radio.value = END_OPTION_END
        view._handle_end_option_change(None)
        assert view.end_time_input.disabled is False
        assert page.updates == 1


class TestToggleTimeInputs:
    def test_unchecked_whole_video_shows_time_row(self):
        view, page, _ = _make()
        view.whole_video_checkbox.value = False
        view._toggle_time_inputs(None)
        assert view._time_visible is True
        assert view.time_row.visible is True
        assert page.updates == 1

    def test_checked_whole_video_hides_time_row(self):
        view, page, _ = _make()
        view.whole_video_checkbox.value = True
        view._toggle_time_inputs(None)
        assert view._time_visible is False
        assert view.time_row.visible is False


class TestToggleReEncode:
    def test_checked_shows_reencode_row_and_saves(self):
        view, page, saved = _make()
        view.re_encode_checkbox.value = True
        view._toggle_re_encode(None)
        assert view._reencode_visible is True
        assert view.re_encode_row.visible is True
        assert saved == [1]
        assert page.updates == 1

    def test_unchecked_hides_reencode_row(self):
        view, page, saved = _make()
        view.re_encode_checkbox.value = False
        view._toggle_re_encode(None)
        assert view._reencode_visible is False
        assert view.re_encode_row.visible is False


class TestUpdateQualities:
    def test_sets_options(self):
        view, _, _ = _make()
        view.update_qualities([1080, 720])
        texts = [o.text for o in view.quality_dropdown.options]
        assert texts == [QUALITY_BEST, "1080p", "720p"]

    def test_keeps_current_when_still_available(self):
        view, page, saved = _make(config={"quality": "720p"})
        view.update_qualities([1080, 720])
        assert view.quality_dropdown.value == "720p"
        assert saved == []

    def test_resets_to_best_when_current_removed(self):
        view, page, saved = _make(config={"quality": "1080p"})
        view.update_qualities([720, 360])
        assert view.quality_dropdown.value == QUALITY_BEST
        assert saved == [1]
        assert page.updates == 1


class TestToParams:
    def test_defaults(self):
        view, _, _ = _make()
        params = view.to_params()
        assert params["whole_video"] is True
        assert params["start_time"] == "00:00:00"
        assert params["end_option"] == END_OPTION_FULL
        assert params["re_encode"] is False
        assert params["crf"] == "23"
        assert params["preset"] == "fast"
        assert params["quality"] == QUALITY_BEST
        assert params["format_choice"] == FORMAT_MP4

    def test_trim_fields(self):
        view, _, _ = _make()
        view.whole_video_checkbox.value = False
        view.start_time_input.value = " 00:01:30 "
        view.end_time_input.value = " 00:02:00 "
        view.end_option_radio.value = END_OPTION_END
        view.re_encode_checkbox.value = True
        view.crf_input.value = "20"
        view.preset_dropdown.value = "slow"
        params = view.to_params()
        assert params["whole_video"] is False
        assert params["start_time"] == "00:01:30"
        assert params["end_time"] == "00:02:00"
        assert params["end_option"] == END_OPTION_END
        assert params["re_encode"] is True
        assert params["crf"] == "20"
        assert params["preset"] == "slow"

    def test_none_values_cleaned(self):
        view, _, _ = _make()
        view.crf_input.value = None
        view.start_time_input.value = None
        params = view.to_params()
        assert params["crf"] == ""
        assert params["start_time"] == ""


class TestCleanText:
    def test_none(self):
        assert QualityView._clean_text(None) == ""

    def test_whitespace(self):
        assert QualityView._clean_text("  x  ") == "x"


class TestConfigApplied:
    def test_widget_values_from_config(self):
        view, _, _ = _make(
            config={"quality": "1080p", "format": "Pouze zvuk (MP3)", "re_encode": True, "crf": "20", "preset": "slow"}
        )
        assert view.quality_dropdown.value == "1080p"
        assert view.format_dropdown.value == "Pouze zvuk (MP3)"
        assert view.re_encode_checkbox.value is True
        assert view.crf_input.value == "20"
        assert view.preset_dropdown.value == "slow"


class TestBuild:
    def test_desktop(self, monkeypatch):
        monkeypatch.setattr(th, "SCREEN_WIDTH", 800)
        view, _, _ = _make()
        result = view.build()
        assert isinstance(result, ft.Column)
        assert view.crf_input.width is not None
        assert view.crf_input.expand == 0

    def test_compact(self, monkeypatch):
        monkeypatch.setattr(th, "SCREEN_WIDTH", 300)
        view, _, _ = _make()
        view.build()
        assert view.crf_input.width is None
        assert view.crf_input.expand == 1
