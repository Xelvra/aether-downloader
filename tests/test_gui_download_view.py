import pytest

from stahovac.core.metadata import MetadataError
from stahovac.gui.download_view import DownloadView
from stahovac.gui.theme import sz
from stahovac.models import VideoMetadata


class _FakePage:
    def update(self):
        pass


class _FakeExecutor:
    def __init__(self):
        self.submitted = []
        self.shutdown_calls = 0

    def submit(self, fn, *args, **kwargs):
        self.submitted.append(fn)
        return None

    def shutdown(self, **kwargs):
        self.shutdown_calls += 1


def _make(meta=None, on_meta=None):
    started = []
    cancelled = []
    page = _FakePage()
    view = DownloadView(
        page,
        metadata_service=meta,
        config={},
        on_start_download=started.append,
        on_cancel_download=lambda: cancelled.append(1),
        on_metadata_fetched=on_meta,
    )
    return view, started, cancelled


def _meta(**overrides):
    data = dict(title="Video", uploader="Autor", duration=90, thumbnail="https://x/thumb.jpg", description="")
    data.update(overrides)
    return VideoMetadata(**data)


class TestInitState:
    def test_cancel_disabled_initially(self):
        view, _, _ = _make()
        assert view.cancel_button.disabled is True

    def test_url_change_wired(self):
        view, _, _ = _make()
        assert view.url_input.on_change == view._on_url_change


class TestHandlers:
    def test_download_click_trims_url(self):
        view, started, _ = _make()
        view.url_input.value = "  https://youtu.be/abc  "
        view._on_download_click(None)
        assert started == ["https://youtu.be/abc"]

    def test_refresh_click_calls_refresh(self, monkeypatch):
        view, _, _ = _make()
        called = []
        monkeypatch.setattr(view, "refresh_metadata", lambda: called.append(1))
        view._on_refresh_click(None)
        assert called == [1]

    def test_url_change_schedules_debounce(self):
        view, _, _ = _make()
        view._on_url_change(None)
        assert view._debounce_timer is not None
        first = view._debounce_timer
        view._on_url_change(None)
        assert view._debounce_timer is not first
        view._debounce_timer.cancel()


class TestRefreshMetadata:
    def _run_worker(self, view):
        fn = view._metadata_executor.submitted[-1]
        fn()

    def test_invalid_url_skips_fetch(self, monkeypatch):
        meta = _FakeMeta()
        view, _, _ = _make(meta=meta)
        view._metadata_executor = _FakeExecutor()
        view.url_input.value = "not a url"
        view.refresh_metadata()
        assert view._metadata_executor.submitted == []

    def test_valid_url_submits_fetch(self):
        meta = _FakeMeta()
        view, _, _ = _make(meta=meta)
        view._metadata_executor = _FakeExecutor()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()
        assert view._metadata_executor.submitted
        view._metadata_executor.submitted[-1]()
        assert meta.fetched == [("https://youtu.be/abc", {})]

    def test_worker_stale_request_id_skipped(self):
        meta = _FakeMeta()
        view, _, _ = _make(meta=meta, on_meta=lambda m: results.append(m))
        results = []
        view._metadata_executor = _FakeExecutor()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()
        view._metadata_request_id += 1  # simulace novějšího požadavku
        self._run_worker(view)
        assert results == []

    def test_worker_last_url_changed_skipped(self):
        meta = _FakeMeta()
        view, _, _ = _make(meta=meta, on_meta=lambda m: results.append(m))
        results = []
        view._metadata_executor = _FakeExecutor()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()
        view._last_url_fetched = "https://youtu.be/other"
        self._run_worker(view)
        assert results == []

    def test_worker_fetch_error_reports_none(self):
        class Boom(_FakeMeta):
            def fetch(self, url, config):
                raise MetadataError("video unavailable")

        view, _, _ = _make(meta=Boom(), on_meta=lambda m: results.append(m))
        results = []
        view._metadata_executor = _FakeExecutor()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()
        self._run_worker(view)
        assert results == [None]

    def test_worker_unexpected_exception_not_swallowed(self):
        class Boom(_FakeMeta):
            def fetch(self, url, config):
                raise RuntimeError("programming error")

        view, _, _ = _make(meta=Boom())
        view._metadata_executor = _FakeExecutor()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()
        with pytest.raises(RuntimeError):
            self._run_worker(view)

    def test_worker_success_calls_callback(self):
        meta = _FakeMeta(result=_meta())
        view, _, _ = _make(meta=meta, on_meta=lambda m: results.append(m))
        results = []
        view._metadata_executor = _FakeExecutor()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()
        self._run_worker(view)
        assert results == [_meta()]


class _FakeMeta:
    def __init__(self, result=None):
        self.fetched = []
        self._result = result

    def fetch(self, url, config):
        self.fetched.append((url, config))
        return self._result


class TestUpdateMetadataUi:
    def test_none_uses_fallbacks(self):
        view, _, _ = _make()
        view.url_input.value = "https://youtu.be/abc"
        view.update_metadata_ui(None)
        assert view.meta_title.value == "https://youtu.be/abc"
        assert view.meta_author.value == "Neznámý kanál"
        assert view.meta_duration.value == "Neznámá délka"
        assert view.thumbnail_img.visible is False
        assert view.metadata_card.visible is True

    def test_metadata_fills_fields(self):
        view, _, _ = _make()
        view.update_metadata_ui(_meta())
        assert view.meta_title.value == "Video"
        assert "Autor" in view.meta_author.value
        assert "Délka:" in view.meta_duration.value
        assert view.thumbnail_img.src == "https://x/thumb.jpg"
        assert view.thumbnail_img.visible is True
        assert view.metadata_card.visible is True

    def test_metadata_without_thumbnail_hides_image(self):
        view, _, _ = _make()
        view.update_metadata_ui(_meta(thumbnail=""))
        assert view.thumbnail_img.visible is False
        assert view.metadata_card.visible is True


class TestSetDownloading:
    def test_active_disables_download(self):
        view, _, _ = _make()
        view.set_downloading(True)
        assert view.download_button.disabled is True
        assert view.cancel_button.disabled is False
        assert view.url_input.disabled is True

    def test_idle_enables_download(self):
        view, _, _ = _make()
        view.set_downloading(True)
        view.set_downloading(False)
        assert view.download_button.disabled is False
        assert view.cancel_button.disabled is True
        assert view.url_input.disabled is False


class TestClose:
    def test_close_is_idempotent_and_shuts_executor_once(self):
        view, _, _ = _make()
        view._metadata_executor = _FakeExecutor()
        view.close()
        view.close()
        assert view._metadata_executor.shutdown_calls == 1
        assert view._debounce_timer is None

    def test_refresh_after_close_does_not_submit(self):
        view, _, _ = _make()
        view._metadata_executor = _FakeExecutor()
        view.close()
        view.url_input.value = "https://youtu.be/abc"
        view.refresh_metadata()
        assert view._metadata_executor.submitted == []


class TestBuildMetadataCard:
    def test_compact_sets_larger_thumbnail(self):
        view, _, _ = _make()
        view._build_metadata_card(compact=True)
        assert view.thumbnail_img.width == sz(180)
        assert view.thumbnail_img.height == sz(101)

    def test_desktop_sets_default_thumbnail(self):
        view, _, _ = _make()
        view._build_metadata_card(compact=False)
        assert view.thumbnail_img.width == sz(160)
        assert view.thumbnail_img.height == sz(90)
