"""The ``info`` endpoint: supported reference systems and the coordinate cap."""

from __future__ import annotations

from . import cache
from .base import MAX_COORD, post

__all__ = ["systems", "system_by_epsg", "info", "MAX_COORD"]


def info() -> dict:
    """Fetch the raw ``info`` response: ``{maxCoord, srsSupportati}``."""
    return post({"richiesta": "info"})


def systems(refresh: bool = False) -> list[dict]:
    """Return the supported reference systems as ``[{"epsg", "descrizione"}, ...]``.

    Prefers the offline cache. On a miss (or ``refresh=True``) it fetches live
    and persists the result. If the live fetch fails but a cache exists, the
    cache is returned.
    """
    if not refresh:
        cached = cache.load_systems()
        if cached:
            return cached
    try:
        resp = info()
    except Exception:
        cached = cache.load_systems()
        if cached:
            return cached
        raise
    srs = resp.get("srsSupportati", []) or []
    if srs:
        cache.save_systems(srs)
    return srs


def system_by_epsg(systems_list: list[dict], epsg: int) -> dict | None:
    for s in systems_list:
        if s.get("epsg") == epsg:
            return s
    return None
