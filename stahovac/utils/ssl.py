"""Přenosné SSL kontexty s CA certifikáty z certifi.

Binárka zkompilovaná PyInstallerem nemá zaručený přístup k systémovému
úložišti CA certifikátů – cesty vestavěné do OpenSSL závisí na tom, kde
a jakým Pythonem se build postavil (lokálně vs. GitHub Actions). Proto se
pro ověřování TLS používá CA bundle z ``certifi``, který je součástí
binárky, takže ověřování funguje stejně na všech systémech.
"""

import logging
import ssl
from functools import lru_cache

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _cafile() -> str | None:
    if certifi is None:
        return None
    try:
        return certifi.where()
    except Exception:  # pragma: no cover
        logger.debug("certifi.where() selhalo", exc_info=True)
        return None


@lru_cache(maxsize=1)
def make_ssl_context() -> ssl.SSLContext:
    """SSL kontext s certifi CA bundle, jinak se systémovým výchozím."""
    cafile = _cafile()
    if cafile:
        try:
            return ssl.create_default_context(cafile=cafile)
        except (OSError, ssl.SSLError):  # pragma: no cover
            logger.debug("Nejde použít certifi CA bundle (%s), fallback na systémový", cafile, exc_info=True)
    return ssl.create_default_context()
