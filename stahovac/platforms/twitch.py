"""Twitch: referer + prohlížečové hlavičky s device ID.

Twitch gql API bez browser hlaviček a stabilního `X-Device-Id` vrací
přechodné HTTP 403 (rate-limit / bot detekce). Device ID je stejné pro
všechny požadavky daného běhu aplikace.
"""

import uuid

from stahovac.platforms.base import BROWSER_HEADERS

hosts = {"twitch.tv"}

ranged_hls = True

_DEVICE_ID = uuid.uuid4().hex


def build_opts(url: str) -> dict:
    headers = dict(BROWSER_HEADERS)
    headers["X-Device-Id"] = _DEVICE_ID
    return {"referer": "https://www.twitch.tv/", "http_headers": headers}
