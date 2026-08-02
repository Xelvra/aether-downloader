from stahovac.core.validator import (
    RE_PROGRESS,
    is_valid_url,
    normalize_time,
    pad_time,
    time_to_seconds,
    validate_time_range,
)


class TestProgressRegex:
    def test_matches_typical_line(self):
        m = RE_PROGRESS.search("[download]  45.2% of  128.00MiB at  5.00MiB/s ETA 00:17")
        assert m is not None
        assert m.group("percent") == "45.2"
        assert m.group("speed") == "5.00MiB/s"
        assert m.group("eta") == "00:17"

    def test_no_match_for_unrelated_line(self):
        assert RE_PROGRESS.search("[Merger] Merging formats into video.mp4") is None


class TestNormalizeTime:
    def test_comma_to_colon(self):
        assert normalize_time("1,30") == "1:30"

    def test_already_colon(self):
        assert normalize_time("1:30") == "1:30"

    def test_no_change_needed(self):
        assert normalize_time("100") == "100"


class TestPadTime:
    def test_seconds_only(self):
        assert pad_time("30") == "00:00:30"
        assert pad_time("5") == "00:00:05"

    def test_minutes_seconds(self):
        assert pad_time("2:30") == "00:02:30"
        assert pad_time("0:45") == "00:00:45"
        assert pad_time("10:05") == "00:10:05"

    def test_hours_minutes_seconds(self):
        assert pad_time("1:30:45") == "01:30:45"
        assert pad_time("0:0:5") == "00:00:05"

    def test_with_commas(self):
        assert pad_time("1,30,45") == "01:30:45"


class TestTimeToSeconds:
    def test_seconds_only(self):
        assert time_to_seconds("30") == 30
        assert time_to_seconds("0") == 0

    def test_minutes_seconds(self):
        assert time_to_seconds("2:30") == 150
        assert time_to_seconds("0:45") == 45

    def test_hours_minutes_seconds(self):
        assert time_to_seconds("1:30:45") == 5445
        assert time_to_seconds("0:0:5") == 5

    def test_with_commas(self):
        assert time_to_seconds("1,30,00") == 5400


class TestValidateTimeRange:
    def test_valid_whole_video(self):
        assert validate_time_range("00:00", "00:00", "Do konce videa") is None

    def test_valid_with_end_time(self):
        assert validate_time_range("00:01:00", "00:02:00", "Do určitého času") is None

    def test_invalid_start_format(self):
        result = validate_time_range("abc", "00:02:00", "Do určitého času")
        assert result is not None
        assert "Neplatný" in result

    def test_invalid_end_format(self):
        result = validate_time_range("00:01:00", "xyz", "Do určitého času")
        assert result is not None
        assert "Neplatný" in result

    def test_start_greater_than_end(self):
        result = validate_time_range("00:05:00", "00:02:00", "Do určitého času")
        assert result is not None
        assert "větší" in result

    def test_start_equal_to_end(self):
        result = validate_time_range("00:02:00", "00:02:00", "Do určitého času")
        assert result is not None
        assert "větší" in result


class TestIsValidUrl:
    def test_valid_https(self):
        assert is_valid_url("https://www.youtube.com/watch?v=123") is True

    def test_valid_http(self):
        assert is_valid_url("http://example.com") is True

    def test_empty_string(self):
        assert is_valid_url("") is False

    def test_only_whitespace(self):
        assert is_valid_url("   ") is False

    def test_no_scheme(self):
        assert is_valid_url("example.com") is False

    def test_no_netloc(self):
        assert is_valid_url("https://") is False
