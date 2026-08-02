"""Kick: yt-dlp opce + fallback na oficiální Kick API (v2) pro VOD.

Kick má vlastní API fallback, protože yt-dlp neumí všechny Kick VOD
(např. ty s číselným id). Ostatní platformy tak zůstávají nedotčené.
"""

import contextlib
import json
import logging
import re
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

from stahovac.utils.ssl import make_ssl_context

logger = logging.getLogger(__name__)

hosts = {"kick.com"}

ranged_hls = True

KICK_API_BASE = "https://kick.com/api"
VOD_URL_RE = re.compile(r"https?://(?:www\.)?kick\.com/(?P<channel>[\w-]+)/videos/(?P<vod_id>[\w-]+)")

_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Referer": "https://kick.com/",
    "Accept": "application/json, text/plain, */*",
}

_VOD_PAGE_M3U8_RE = re.compile(r'https?://[^"\\ ]+\.m3u8\?token=[^"\\ ]+')

_VOD_TITLE_RE = re.compile(r'\\"title\\":\\"([^"]*)\\"')
_VOD_LANG_RE = re.compile(r'\\"language\\":\\"([^"]+)\\"')
_VOD_THUMB_RE = re.compile(r'\\"thumbnail\\":\{\\"src\\":\\"([^"]+)\\"')
_VOD_VIEWERS_RE = re.compile(r'\\"viewer_count\\":(\d+)')


def build_opts(url: str) -> dict:
    return {"referer": "https://kick.com/"}


class _KickCancelError(Exception):
    pass


class KickAdapter:
    """Adaptér nad Kick API fallbackem – stabilní rozhraní nezávislé na interním patchování yt-dlp."""

    @staticmethod
    def supports(url: str) -> bool:
        return parse_vod_url(url) is not None

    @staticmethod
    def extract(url: str, cancel_check=None, auth_token: str | None = None) -> dict | None:
        data = fetch_vod_data(url, cancel_check=cancel_check, **_auth_kwargs(auth_token))
        if data:
            return build_ytdlp_info(data, cancel_check=cancel_check, **_auth_kwargs(auth_token))
        page_data = _fetch_vod_page(url, cancel_check=cancel_check, **_auth_kwargs(auth_token))
        if page_data:
            return build_ytdlp_info(page_data, cancel_check=cancel_check, **_auth_kwargs(auth_token))
        resolved = _resolve_vod_id(url, cancel_check=cancel_check, **_auth_kwargs(auth_token))
        if resolved:
            return build_ytdlp_info(resolved, cancel_check=cancel_check, **_auth_kwargs(auth_token))
        return None


def _check_cancel(cancel_check) -> None:
    if cancel_check is not None and cancel_check():
        raise _KickCancelError()


def _auth_kwargs(auth_token: str | None) -> dict:
    return {"auth_token": auth_token} if auth_token else {}


def parse_vod_url(url: str) -> tuple[str, str] | None:
    m = VOD_URL_RE.match(url.rstrip("/"))
    if m:
        return m.group("channel"), m.group("vod_id")
    return None


def _api_get(path: str, timeout: int = 15, cancel_check=None, auth_token: str | None = None) -> dict | list | None:
    _check_cancel(cancel_check)
    ctx = make_ssl_context()
    headers = dict(_API_HEADERS)
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    req = urllib.request.Request(f"{KICK_API_BASE}/{path}", headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        payload: dict | list | None = json.loads(resp.read().decode())
        return payload
    except _KickCancelError:
        raise
    except HTTPError as e:
        logger.debug("Kick API %s -> %s %s", path, e.code, e.reason)
        return None
    except (URLError, TimeoutError, OSError) as e:
        logger.debug("Kick API %s network error: %s", path, e)
        return None
    except Exception as e:
        logger.warning("Kick API %s unexpected error: %r", path, e)
        return None


def _normalize_v1_video(resp: dict, channel: str) -> dict | None:
    ls = resp.get("livestream") or {}
    if not isinstance(ls, dict) or not ls.get("id"):
        return None
    ls_cats = ls.get("categories") or []
    return {
        "id": ls.get("id"),
        "slug": ls.get("slug"),
        "session_title": ls.get("session_title"),
        "source": resp.get("source") or "",
        "duration": ls.get("duration") or 0,
        "language": ls.get("language") or "",
        "view_count": resp.get("views") or 0,
        "thumbnail": ls.get("thumbnail") or {},
        "categories": ls_cats,
        "video": {
            "id": resp.get("id"),
            "uuid": resp.get("uuid"),
            "source": resp.get("source") or "",
        },
        "user": ls.get("user") or {},
        "channel": channel or ls.get("slug") or "",
    }


def fetch_vod_data(url: str, cancel_check=None, auth_token: str | None = None) -> dict | None:
    parsed = parse_vod_url(url)
    if not parsed:
        return None
    channel, vod_id = parsed

    if auth_token:
        direct = _api_get(f"v1/video/{vod_id}", cancel_check=cancel_check, auth_token=auth_token)
        if isinstance(direct, dict):
            normalized = _normalize_v1_video(direct, channel)
            if normalized:
                logger.info("Kick VOD %s resolved directly with auth", vod_id)
                return normalized

    vods = _api_get(f"v2/channels/{channel}/videos", cancel_check=cancel_check, **_auth_kwargs(auth_token))
    if not isinstance(vods, list):
        return None

    for item in vods:
        _check_cancel(cancel_check)
        if not isinstance(item, dict):
            continue
        video = item.get("video") or {}
        uuid = video.get("uuid", "")
        if uuid and uuid == vod_id:
            return item

    logger.debug("Kick VOD %s/%s not in channel list by uuid", channel, vod_id)
    return None


def _re_group(pattern: "re.Pattern", text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def _fetch_vod_page(url: str, cancel_check=None, auth_token: str | None = None) -> dict | None:
    """Fallback: sub-only Kick VODy nejsou dostupné přes `v1/video` API, ale stránka VOD
    je (s cookies) vrátí včetně podepsaného `playback_url`. Data vytáhneme z RSC payloadu."""
    parsed = parse_vod_url(url)
    if not parsed:
        return None
    channel, vod_id = parsed

    page = _fetch_url(url, cancel_check=cancel_check, **_auth_kwargs(auth_token))
    if not page:
        return None

    obj_pat = re.compile(
        r'\\"category\\":\{\\"id\\":(\d+),\\"name\\":\\"([^"]+)\\",\\"slug\\":\\"([^"]+)\\"\},'
        r'\\"channel\\":\{\\"id\\":(\d+),\\"slug\\":\\"([^"]+)\\",\\"username\\":\\"([^"]+)\\"\},'
        r'\\"duration\\":(\d+),\\"end_time\\":\\"[^"]*\\",\\"id\\":\\"' + re.escape(vod_id) + r'\\"'
    )
    obj = obj_pat.search(page)
    if not obj:
        logger.debug("Kick VOD page %s: video object not found", vod_id)
        return None

    # Playback URL se hledá jen v regionu VOD objektu, ne na celé stránce –
    # stránka může obsahovat live player kanálu, jehož m3u8 by jinak seděl dřív.
    m3u8 = _VOD_PAGE_M3U8_RE.search(page[obj.start() : obj.end() + 4000])
    if not m3u8:
        logger.debug("Kick VOD page %s: playback URL not found in VOD region", vod_id)
        return None
    source = m3u8.group(0)

    tail = page[obj.end() : obj.end() + 2000]
    title = _re_group(_VOD_TITLE_RE, tail)
    category_name = obj.group(2)
    channel_slug = obj.group(5) or channel
    duration_ms = (int(obj.group(7) or 0)) * 1000

    data = {
        "id": vod_id,
        "slug": title or "",
        "session_title": title or "",
        "source": source,
        "duration": duration_ms,
        "language": _re_group(_VOD_LANG_RE, tail) or "",
        "view_count": int(_re_group(_VOD_VIEWERS_RE, tail) or 0),
        "thumbnail": {"src": _re_group(_VOD_THUMB_RE, tail) or ""},
        "categories": [{"name": category_name}] if category_name else [],
        "video": {"id": "", "uuid": vod_id, "source": source},
        "user": {"id": obj.group(4), "username": obj.group(6)},
        "channel": channel_slug,
    }
    logger.info("Kick VOD %s resolved from page scrape", vod_id)
    return data


def _resolve_vod_id(url: str, cancel_check=None, auth_token: str | None = None) -> dict | None:
    parsed = parse_vod_url(url)
    if not parsed:
        return None
    channel, vod_id = parsed

    vods = _api_get(f"v2/channels/{channel}/videos", cancel_check=cancel_check, **_auth_kwargs(auth_token))
    if not isinstance(vods, list) or not vods:
        logger.debug("No VODs found for channel %s", channel)
        return None

    for item in vods:
        _check_cancel(cancel_check)
        if not isinstance(item, dict):
            continue
        video = item.get("video") or {}
        uuid = video.get("uuid", "")
        if not uuid:
            continue

        resp = _api_get(f"v1/video/{uuid}", cancel_check=cancel_check, **_auth_kwargs(auth_token))
        if not isinstance(resp, dict):
            continue

        ls = resp.get("livestream") or {}
        if ls.get("vod_id") == vod_id:
            logger.info("Kick VOD %s resolved to uuid %s", vod_id, uuid)
            return _normalize_v1_video(resp, channel)

    logger.warning("Kick VOD %s/%s not resolved from channel VOD list", channel, vod_id)
    return None


def _fetch_url(url: str, timeout: int = 15, cancel_check=None, auth_token: str | None = None) -> str | None:
    _check_cancel(cancel_check)
    headers = dict(_API_HEADERS)
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    req = urllib.request.Request(url, headers=headers)
    ctx = make_ssl_context()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        body: str | None = resp.read().decode("utf-8", errors="replace")
        return body
    except _KickCancelError:
        raise
    except (URLError, TimeoutError, OSError) as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None
    except Exception as e:
        logger.warning("Failed to fetch %s – unexpected error: %r", url, e)
        return None


def _make_format(
    media_url: str,
    manifest_url: str,
    height: int | None,
    width: int | None,
    bandwidth: int | None,
    is_audio_only: bool = False,
    auth_token: str | None = None,
) -> dict:
    fragment_base = media_url.rsplit("/", 1)[0] + "/"
    fmt_id = f"hls-{height}" if height else f"hls-{bandwidth}" if bandwidth else "hls"

    http_headers = dict(_API_HEADERS)
    if auth_token:
        http_headers["Authorization"] = f"Bearer {auth_token}"

    fmt: dict = {
        "url": media_url,
        "ext": "mp4",
        "protocol": "m3u8_native",
        "format": fmt_id,
        "format_id": fmt_id,
        "tbr": bandwidth // 1000 if bandwidth else None,
        "fragment_base_url": fragment_base,
        "manifest_url": manifest_url,
        "http_headers": http_headers,
    }

    if is_audio_only:
        fmt["height"] = None
        fmt["width"] = None
        fmt["vcodec"] = "none"
        fmt["acodec"] = "aac"
    else:
        fmt["height"] = height
        fmt["width"] = width
        fmt["vcodec"] = "h264"
        fmt["acodec"] = "aac"

    return fmt


def _parse_master_playlist(content: str, base_url: str, auth_token: str | None = None) -> list[dict]:
    formats: list[dict] = []
    lines = content.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs_str = line[len("#EXT-X-STREAM-INF:") :]
            attrs = {}
            for attr in attrs_str.split(","):
                if "=" in attr:
                    key, value = attr.split("=", 1)
                    attrs[key.strip()] = value.strip().strip('"')

            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
                i += 1

            if i < len(lines):
                media_url = lines[i].strip()
                if not media_url.startswith("http"):
                    media_url = urllib.parse.urljoin(base_url, media_url)

                resolution = attrs.get("RESOLUTION", "")
                width = height = 0
                bandwidth = 0
                try:
                    if "x" in resolution:
                        parts = resolution.split("x")
                        if len(parts) == 2:
                            width = int(parts[0])
                            height = int(parts[1])
                    bandwidth = int(attrs.get("BANDWIDTH", 0))
                except ValueError:
                    width = height = 0
                    bandwidth = 0
                codecs = attrs.get("CODECS", "")
                is_audio_only = "mp4a" in codecs and "avc" not in codecs and "hvc" not in codecs

                fmt = _make_format(
                    media_url=media_url,
                    manifest_url=base_url,
                    height=height if height else None,
                    width=width if width else None,
                    bandwidth=bandwidth,
                    is_audio_only=is_audio_only,
                    auth_token=auth_token,
                )
                formats.append(fmt)
        i += 1

    return formats


def _build_hls_formats(source: str, cancel_check=None, auth_token: str | None = None) -> list[dict]:
    if not source:
        return []

    playlist = _fetch_url(source, cancel_check=cancel_check, **_auth_kwargs(auth_token))
    if not playlist:
        logger.warning("Cannot fetch HLS playlist from %s, using single format", source)
        return [_make_format(source, source, 1080, 1920, None, auth_token=auth_token)]

    if "#EXT-X-STREAM-INF:" in playlist:
        formats = _parse_master_playlist(playlist, source, auth_token=auth_token)
        if formats:
            logger.info("Parsed %d quality variants from master playlist", len(formats))
            return formats
        logger.warning("Master playlist had no variants, falling back to single format")

    return [_make_format(source, source, 1080, 1920, None, auth_token=auth_token)]


def build_ytdlp_info(vod: dict, cancel_check=None, auth_token: str | None = None) -> dict:
    video = vod.get("video") or {}
    cat_list = vod.get("categories") or []

    title = vod.get("session_title") or vod.get("slug") or "Unknown"
    duration_ms = vod.get("duration") or 0
    source = vod.get("source") or video.get("source") or ""

    thumbnail = ""
    thumb_data = vod.get("thumbnail") or {}
    if isinstance(thumb_data, dict):
        thumbnail = thumb_data.get("src") or thumb_data.get("url") or ""
    elif isinstance(thumb_data, str):
        thumbnail = thumb_data

    user = vod.get("user") or {}
    uploader = user.get("username") or vod.get("slug") or ""
    uploader_id = str(user.get("id") or vod.get("channel_id") or "")
    channel = vod.get("channel") or ""

    categories = []
    for c in cat_list:
        if isinstance(c, dict):
            name = c.get("name") or c.get("slug", "")
            if name:
                categories.append(name)
        elif isinstance(c, str):
            categories.append(c)

    formats = _build_hls_formats(source, cancel_check=cancel_check, **_auth_kwargs(auth_token))

    return {
        "id": str(vod.get("id") or video.get("id") or ""),
        "title": title,
        "ext": "mp4",
        "uploader": uploader,
        "uploader_id": uploader_id,
        "channel": channel,
        "channel_id": str(vod.get("channel_id") or ""),
        "description": "",
        "duration": duration_ms / 1000.0 if duration_ms else 0,
        "thumbnail": thumbnail,
        "view_count": vod.get("views") or 0,
        "language": vod.get("language") or "",
        "categories": categories,
        "formats": formats,
    }


def _session_token_from_extractor(extractor) -> str | None:
    """Kick `session_token` cookie z downloaderu (respektuje cookiesfrombrowser/cookiefile)."""
    try:
        cookies = extractor._get_cookies("https://kick.com/")
        if "session_token" in cookies:
            return urllib.parse.unquote(cookies["session_token"].value)
    except Exception:
        logger.debug("Cannot read Kick session_token cookie", exc_info=True)
    return None


def _cookie_source_hint(extractor) -> str:
    """Nápověda do chybové hlášky, když chybí session_token kvůli nečitelným cookies."""
    try:
        params = extractor._downloader.params or {}
        browser = params.get("cookiesfrombrowser")
        if browser and isinstance(browser, (list, tuple)) and str(browser[0]).lower() == "safari":
            return (
                " (cookies Safari se nepodařilo načíst – povol aplikaci „Plný přístup k disku“ "
                "v Systémovém nastavení, nebo zvol Chrome/Firefox/cookies.txt)"
            )
    except Exception:
        pass
    return ""


def patch_ytdlp_extractor():
    try:
        from yt_dlp.extractor.kick import KickVODIE
    except ImportError:
        logger.warning("Cannot patch KickVODIE - import failed")
        return

    _check_ytdlp_version()

    new_pattern = r"https?://(?:www\.)?kick\.com/[\w-]+/videos/(?P<id>[\w-]+)"

    KickVODIE._VALID_URL = new_pattern

    with contextlib.suppress(AttributeError):
        del KickVODIE._VALID_URL_RE

    lazy_mod = __import__("yt_dlp.extractor.lazy_extractors", fromlist=["lazy_extractors"])

    lazy_kick_vod = getattr(lazy_mod, "KickVODIE", None)
    if lazy_kick_vod is not None:
        for attr in ("_VALID_URL", "_VALID_URL_RE"):
            with contextlib.suppress(AttributeError):
                type.__delattr__(lazy_kick_vod, attr)
        lazy_kick_vod._VALID_URL = new_pattern

    orig_extract = KickVODIE._real_extract

    def _patched_extract(self, url):
        video_id = self._match_id(url)
        cancel_check = None
        with contextlib.suppress(AttributeError):
            cancel_check = self._downloader.params.get("_cancel_check")
        auth_token = _session_token_from_extractor(self)

        try:
            return orig_extract(self, url)
        except Exception as e:
            logger.debug("KickVODIE v1 failed for %s: %s", video_id, e)

        try:
            data = KickAdapter.extract(url, cancel_check=cancel_check, auth_token=auth_token)
            if data:
                return data
        except _KickCancelError:
            from yt_dlp.utils import DownloadError

            raise DownloadError("Stahování zrušeno uživatelem") from None

        from yt_dlp.utils import ExtractorError

        raise ExtractorError(
            f"Kick VOD {video_id} not found (deleted or unavailable){_cookie_source_hint(self)}",
            expected=True,
        )

    KickVODIE._real_extract = _patched_extract
    logger.info("KickVODIE patched - v2 API fallback active")


def _check_ytdlp_version() -> None:
    try:
        from yt_dlp.version import __version__

        parts = __version__.split(".")
        major, minor = int(parts[0]), int(parts[1])
        if (major, minor) < (2024, 12):
            logger.warning(
                "yt-dlp %s is below tested version 2024.12 – KickVODIE patch may be incompatible",
                __version__,
            )
    except (ImportError, ValueError, IndexError):
        pass
