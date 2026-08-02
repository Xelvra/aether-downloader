from stahovac.downloader import DownloadManager
from stahovac.models import DownloadParams, DownloadState


def _params(**overrides):
    params = DownloadParams(
        url="https://www.youtube.com/watch?v=abc",
        quality="best",
        format_choice="Video + audio (MP4)",
        output_folder="/tmp/out",
    )
    return params if not overrides else DownloadParams.from_dict({**params.to_dict(), **overrides})


class TestDownloadManager:
    def _make(self, tmp_path, **callbacks):
        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        return DownloadManager(**callbacks)

    def test_construction_defaults(self, tmp_path):
        manager = self._make(tmp_path)
        assert manager.download_state == DownloadState.IDLE
        assert manager.active_job_id is None
        assert manager.downloader is not None

    def test_start_download_sets_state(self, tmp_path):
        manager = self._make(tmp_path)
        started = []

        def fake_start(params, job_id=None):
            started.append((params, job_id))
            return True

        manager._downloader.start = fake_start
        result = manager.start_download(_params())
        assert result is True
        assert manager.download_state == DownloadState.DOWNLOADING
        assert manager.active_job_id is not None
        assert len(started) == 1
        assert started[0][1] == manager.active_job_id

    def test_start_download_rejected_resets_state(self, tmp_path):
        manager = self._make(tmp_path)
        manager._downloader.start = lambda params, job_id=None: False
        result = manager.start_download(_params())
        assert result is False
        assert manager.download_state == DownloadState.IDLE
        assert manager.active_job_id is None

    def test_start_after_finish_transitions_to_downloading(self, tmp_path):
        manager = self._make(tmp_path)
        manager._active_job_id = "j1"
        manager._wrap_finish("j1", True, "Úspěch")
        assert manager.download_state == DownloadState.FINISHED

        manager._downloader.start = lambda params, job_id=None: True
        result = manager.start_download(_params())
        assert result is True
        assert manager.download_state == DownloadState.DOWNLOADING

    def test_start_download_refuses_when_busy(self, tmp_path):
        manager = self._make(tmp_path)
        started = []
        manager._downloader.is_busy = lambda: True
        manager._downloader.start = lambda params, job_id=None: started.append(params)
        result = manager.start_download(_params())
        assert result is False
        assert started == []

    def test_cancel_download(self, tmp_path):
        manager = self._make(tmp_path)
        cancelled = []
        manager._downloader.cancel = lambda: cancelled.append(True)
        manager.cancel_download()
        assert cancelled == [True]

    def test_cancel_sets_cancelling_state(self, tmp_path):
        manager = self._make(tmp_path)
        manager._download_state = DownloadState.DOWNLOADING
        manager._downloader.cancel = lambda: None
        manager.cancel_download()
        assert manager.download_state == DownloadState.CANCELLING

    def test_cancel_while_worker_alive_blocks_new_download(self, tmp_path):
        import threading

        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        manager = self._make(tmp_path)
        release = threading.Event()
        manager._downloader._download_worker = lambda params, job_id: release.wait(timeout=5)

        assert manager.start_download(_params()) is True
        assert manager.download_state == DownloadState.DOWNLOADING
        assert manager.is_busy()

        manager.cancel_download()
        assert manager.download_state == DownloadState.CANCELLING

        # Worker stále žije -> nová úloha je odmítnuta.
        assert manager.start_download(_params()) is False

        # Worker skončí -> nová úloha je přijata.
        release.set()
        manager._downloader._thread.join(timeout=5)
        assert manager.is_busy() is False
        assert manager.start_download(_params()) is True
        manager._downloader.cancel()

    def test_cancel_end_to_end_reports_status(self, tmp_path):
        import threading
        import time

        from stahovac.utils.paths import set_base_dir

        set_base_dir(tmp_path)
        statuses, finishes = [], []
        manager = self._make(
            tmp_path,
            on_status=lambda jid, t, c: statuses.append(t),
            on_finish=lambda jid, s, m: finishes.append((jid, s, m)),
        )
        dl = manager.downloader
        dl._get_title = lambda url: "Mock Title"
        entered = threading.Event()

        def fake_download(url, opts, job_id):
            entered.set()
            while not dl.is_cancelled:
                time.sleep(0.005)
            return False

        dl._download_with_ytdlp = fake_download
        assert manager.start_download(_params(output_folder=str(tmp_path), whole_video=True))
        assert entered.wait(5)
        manager.cancel_download()
        dl._thread.join(timeout=5)
        assert "Stahování zrušeno." in statuses
        assert manager.download_state == DownloadState.CANCELLED
        assert finishes[0][1:] == (False, "Zrušeno")

    def test_finish_event_clears_active_job(self, tmp_path):
        received = []
        manager = self._make(tmp_path, on_finish=lambda jid, s, m: received.append((jid, s, m)))
        manager._active_job_id = "current"
        manager._wrap_finish("current", True, "Úspěch")
        assert received == [("current", True, "Úspěch")]
        assert manager.active_job_id is None

    def test_cancelled_state_preserved_on_finish(self, tmp_path):
        manager = self._make(tmp_path)
        manager._download_state = DownloadState.CANCELLED
        manager._active_job_id = "current"
        manager._wrap_finish("current", False, "Zrušeno")
        assert manager.download_state == DownloadState.CANCELLED
        assert manager.active_job_id is None

    def test_failed_state_set_on_regular_failure(self, tmp_path):
        manager = self._make(tmp_path)
        manager._active_job_id = "current"
        manager._wrap_finish("current", False, "Stahování selhalo")
        assert manager.download_state == DownloadState.FAILED

    def test_stale_events_from_old_job_ignored(self, tmp_path):
        received = []
        manager = self._make(tmp_path, on_finish=lambda jid, s, m: received.append((jid, s, m)))
        manager._active_job_id = "current"
        manager._wrap_finish("old", False, "zastaralé")
        assert received == []

    def test_state_callback_updates_download_state(self, tmp_path):
        manager = self._make(tmp_path)
        manager._wrap_state(DownloadState.FETCHING_METADATA)
        assert manager.download_state == DownloadState.FETCHING_METADATA

    def test_progress_active_job_forwards_to_callback(self, tmp_path):
        received = []
        manager = self._make(tmp_path, on_progress=lambda jid, p, s, e: received.append((jid, p, s, e)))
        manager._active_job_id = "j1"
        manager._wrap_progress("j1", 50.0, "1 MB/s", "30s")
        assert received == [("j1", 50.0, "1 MB/s", "30s")]

    def test_progress_stale_job_ignored(self, tmp_path):
        received = []
        manager = self._make(tmp_path, on_progress=lambda jid, p, s, e: received.append(jid))
        manager._active_job_id = "j1"
        manager._wrap_progress("old", 10.0, "", "")
        assert received == []

    def test_config_save(self, tmp_path):
        manager = self._make(tmp_path)
        assert manager.config_save({"quality": "1080p"}) is True

    def test_default_callbacks_noop(self, tmp_path):
        manager = self._make(tmp_path)
        manager.downloader.on_log("x")
        manager.downloader.on_progress("j1", 0.0, "x", "y")
        manager.downloader.on_status("j1", "x", "red")
        manager.downloader.on_finish("j1", True, "ok")
