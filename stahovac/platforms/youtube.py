"""YouTube: stabilnější player client pro načtení metadat a streamů.

``web_embedded`` vrací plné rozlišení (až 4K) bez PO tokenu; ``android``
je spolehlivý fallback, který ale omezuje na 360p; ``android_vr`` přidává
4K/1440p, kde to YouTube dovolí. Kombinace zajistí, že se vždy najde
formát a pokud možno v plné kvalitě.
"""

hosts = {"youtube.com", "youtu.be"}


def build_opts(url: str) -> dict:
    return {"extractor_args": {"youtube": {"player_client": ["android", "web_embedded", "android_vr"]}}}
