from stahovac.core.downloader import _format_eta, _format_speed


class TestFormatSpeed:
    def test_none(self):
        assert _format_speed(None) == "–"

    def test_bytes(self):
        assert _format_speed(500) == "500 B/s"

    def test_kilobytes(self):
        assert _format_speed(1500) == "2 kB/s"
        assert _format_speed(999_999) == "1000 kB/s"

    def test_megabytes(self):
        assert _format_speed(1_000_000) == "1.0 MB/s"
        assert _format_speed(5_500_000) == "5.5 MB/s"


class TestFormatEta:
    def test_none(self):
        assert _format_eta(None) == "–"

    def test_seconds(self):
        assert _format_eta(30) == "30s"
        assert _format_eta(0) == "0s"

    def test_minutes(self):
        assert _format_eta(60) == "1m 0s"
        assert _format_eta(150) == "2m 30s"

    def test_hours(self):
        assert _format_eta(3600) == "1h 0m"
        assert _format_eta(3660) == "1h 1m"
        assert _format_eta(7380) == "2h 3m"
