"""GeoIP resolver — maps a client IP to a 2-letter ISO country code.

Offline by design: uses a local MaxMind GeoLite2-Country database via the
optional ``geoip2`` dependency. Zero extra-request latency and no external
service call on the auth path.

If the ``geoip2`` library is not installed, the settings path is empty, or
the file is missing, the module falls back to a ``NoopResolver`` that
always returns ``None``. Callers treat ``None`` as "unknown" and move on —
authentication never blocks on geolocation.
"""
from __future__ import annotations

import ipaddress
import logging
from pathlib import Path
from typing import Protocol

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


class GeoIPResolver(Protocol):
    """Minimal surface area: one lookup, nullable ISO-3166-1 alpha-2 code."""

    def lookup_country(self, ip: str) -> str | None: ...


def _is_private_ip(ip: str) -> bool:
    """Return True for loopback / link-local / private / reserved addresses.

    MaxMind doesn't answer for these ranges, so don't waste a DB hit.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


class NoopResolver:
    """Fallback resolver used when no MaxMind DB is configured/available."""

    def lookup_country(self, _ip: str) -> str | None:
        return None


class MaxMindResolver:
    """GeoIPResolver backed by a local MaxMind GeoLite2-Country ``.mmdb`` file.

    The reader is opened once at construction and reused for every lookup.
    Any lookup error is swallowed and returns ``None`` — this path must
    never raise into authentication code.
    """

    def __init__(self, db_path: str) -> None:
        import geoip2.database  # local import: dep is optional

        self._reader = geoip2.database.Reader(db_path)

    def lookup_country(self, ip: str) -> str | None:
        if not ip or _is_private_ip(ip):
            return None
        try:
            response = self._reader.country(ip)
        except Exception as exc:  # geoip2.errors.AddressNotFoundError, etc.
            logger.debug("GeoIP lookup failed for %s: %s", ip, exc)
            return None
        iso = getattr(response.country, "iso_code", None)
        if iso:
            return str(iso).upper()
        return None


class _ResolverState:
    resolver: GeoIPResolver | None = None


def _build_resolver() -> GeoIPResolver:
    """Pick the best available resolver from current settings.

    Rules:
      * ``geoip_db_path`` empty → Noop
      * path set but file missing → Noop (log once)
      * ``geoip2`` import fails → Noop (log once)
      * otherwise → MaxMindResolver
    """
    db_path = settings.geoip_db_path
    if not db_path:
        return NoopResolver()
    if not Path(db_path).is_file():
        logger.warning(
            "GeoIP DB path %s not found; falling back to NoopResolver",
            db_path,
        )
        return NoopResolver()
    try:
        return MaxMindResolver(db_path)
    except ImportError:
        logger.warning(
            "geoip2 library not installed; GeoIP lookups disabled",
        )
        return NoopResolver()
    except Exception as exc:
        logger.warning(
            "Failed to open GeoIP DB at %s (%s); falling back to NoopResolver",
            db_path,
            exc,
        )
        return NoopResolver()


def get_resolver() -> GeoIPResolver:
    """Return the process-wide resolver, lazy-initialising from settings."""
    if _ResolverState.resolver is None:
        _ResolverState.resolver = _build_resolver()
    return _ResolverState.resolver


def set_resolver(resolver: GeoIPResolver | None) -> None:
    """Install or clear the process-wide resolver (test hook)."""
    _ResolverState.resolver = resolver


__all__ = [
    "GeoIPResolver",
    "MaxMindResolver",
    "NoopResolver",
    "get_resolver",
    "set_resolver",
]
