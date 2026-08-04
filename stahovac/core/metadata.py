import logging
import threading
from collections.abc import Callable

import yt_dlp

from stahovac.models import VideoMetadata
from stahovac.platforms import platform_opts
from stahovac.utils.cookies import resolve_cookies_opts

logger = logging.getLogger(__name__)


class YtdlLogger:
    def debug(self, msg):
        logger.debug("yt-dlp: %s", msg)

    def warning(self, msg):
        logger.warning("yt-dlp: %s", msg)

    def error(self, msg):
        logger.error("yt-dlp: %s", msg)


class MetadataService:
    def __init__(self, cache_max: int = 50, log_callback=None):
        self._cache: dict[str, VideoMetadata] = {}
        self._info_cache: dict[str, dict] = {}
        self._cache_max = cache_max
        self._cache_lock = threading.Lock()
        self._log = log_callback or (lambda text: None)

    def get_cached(self, url: str) -> VideoMetadata | None:
        with self._cache_lock:
            return self._cache.get(url)

    def fetch(
        self, url: str, config: dict, extra_opts: dict | None = None, cancel_check: Callable[[], bool] | None = None
    ) -> VideoMetadata | None:
        """Blokující fetch bez vlákna – volá se z vlastního vlákna."""
        with self._cache_lock:
            cached = self._cache.get(url)
            if cached:
                return cached

        self.fetch_info(url, config, extra_opts, cancel_check)
        with self._cache_lock:
            return self._cache.get(url)

    def fetch_info(
        self,
        url: str,
        config: dict,
        extra_opts: dict | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict | None:
        """Vrátí surová yt-dlp data (včetně `formats`) – používá se pro ranged HLS stahování."""
        with self._cache_lock:
            cached = self._info_cache.get(url)
            if cached:
                return cached

        info = self._extract_impl(url, config, extra_opts, cancel_check)
        if info:
            self._store_info(url, info)
        return info

    def fetch_sync(
        self,
        url: str,
        config: dict,
        cancel_check: Callable[[], bool] | None = None,
        extra_opts: dict | None = None,
    ) -> VideoMetadata | None:
        with self._cache_lock:
            cached = self._cache.get(url)
            if cached:
                return cached

        result_container: list[VideoMetadata | None] = [None]
        error_container: list[str | None] = [None]

        def worker():
            try:
                result_container[0] = self.fetch(url, config, extra_opts, cancel_check)
            except Exception as e:
                error_container[0] = str(e)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while t.is_alive():
            if cancel_check is not None and cancel_check():
                return None
            t.join(timeout=0.3)

        if error_container[0]:
            self._log(f"Nemohu načíst metadata: {error_container[0][:200]}")
            logger.warning("Metadata fetch error for %s: %s", url, error_container[0])
            return None

        return result_container[0]

    def _extract_impl(
        self, url: str, config: dict, extra_opts: dict | None = None, cancel_check: Callable[[], bool] | None = None
    ) -> dict | None:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 15,
            "retries": 5,
            "extractor_retries": 3,
            "js_runtimes": {"node": {}},
            "logger": YtdlLogger(),
        }
        if cancel_check is not None:
            opts["_cancel_check"] = cancel_check
        opts.update(resolve_cookies_opts(config, url))
        opts.update(platform_opts(url))
        if extra_opts:
            opts.update(extra_opts)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info or None

    def _evict_if_needed(self) -> None:
        """Po překročení `cache_max` vyhodí nejstarší vložené položky (FIFO)."""
        while len(self._cache) > self._cache_max:
            del self._cache[next(iter(self._cache))]
        while len(self._info_cache) > self._cache_max:
            del self._info_cache[next(iter(self._info_cache))]

    def _store_info(self, url: str, info: dict) -> None:
        with self._cache_lock:
            self._info_cache[url] = info
            video = VideoMetadata.from_dict(info)
            formats = info.get("formats") or []
            heights = sorted(
                {f.get("height") for f in formats if isinstance(f.get("height"), int)},
                reverse=True,
            )
            video.available_resolutions = heights
            self._cache[url] = video
            self._evict_if_needed()

    def _add_to_cache(self, url: str, data: VideoMetadata) -> None:
        """Testovací seed helper – naplní cache přímo bez network volání.

        Produkční cesta jde přes `_store_info` (přes `fetch_info`/`fetch`).
        Tuto metodu volají jen testy, aby do cache nahrály data bez yt-dlp.
        """
        with self._cache_lock:
            self._cache[url] = data
            self._evict_if_needed()
