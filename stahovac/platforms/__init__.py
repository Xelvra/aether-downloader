"""Registr platforem.

Každá platforma je samostatný modul se dvěma atributy:
  - `hosts`       – přípony hostů, které patří dané platformě (např. {"kick.com"})
  - `build_opts(url)` – vrací dict yt-dlp opcí specifických pro platformu

Volitelně může definovat `patch_ytdlp_extractor()` pro zásahy do yt-dlp
(pouze pokud to konkrétní web nutně potřebuje).

Přidání nové platformy = vytvořit modul a zaregistrovat ho v `PLATFORMS`.
Sdílený základ se nikdy nesmí měnit kvůli jedné platformě.
"""

from urllib.parse import urlparse

from stahovac.platforms import base, kick, twitch, youtube

PLATFORMS = [youtube, kick, twitch]


def _platform_for(url: str):
    host = (urlparse(url).hostname or "").lower()
    for module in PLATFORMS:
        if any(host == h or host.endswith("." + h) for h in module.hosts):
            return module
    return None


def platform_opts(url: str) -> dict:
    """Sjednotí sdílené opce (base) s opcemi konkrétní platformy."""
    module = _platform_for(url)
    opts = dict(base.base_opts(url))
    if module is not None:
        opts.update(module.build_opts(url))
    return opts


def patch_platform_extractors() -> None:
    """Aplikuje zásahy do yt-dlp pro platformy, které to potřebují (nyní jen Kick)."""
    for module in PLATFORMS:
        patch = getattr(module, "patch_ytdlp_extractor", None)
        if patch is not None:
            patch()
