"""Offline write-through cache for systems and conversion results.

Cached results let pipelines replay the same conversions offline and keep CI
runs reproducible without hitting the live service. Files live under the user
cache directory (``platformdirs``); set ``OPENVERTO_CACHE_DIR`` to override.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_cache_dir

# Conversion cache keys round e/n to this many decimals so float jitter on the
# input does not prevent a hit. 6 decimals is ~0.1 mm at the equator — finer
# than the service's own precision.
_KEY_DECIMALS = 6


def cache_dir() -> Path:
    """Return the cache directory, honouring ``OPENVERTO_CACHE_DIR``."""
    override = os.environ.get("OPENVERTO_CACHE_DIR")
    d = Path(override) if override else Path(user_cache_dir("openverto"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _systems_file() -> Path:
    return cache_dir() / "systems.json"


def _conv_file() -> Path:
    return cache_dir() / "conversions.json"


def load_systems() -> list[dict]:
    """Return the cached systems list, or ``[]`` on miss/corruption."""
    f = _systems_file()
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_systems(systems: list[dict]) -> None:
    try:
        _systems_file().write_text(
            json.dumps(systems, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def _conv_key(in_epsg: int, out_epsg: int, e: float, n: float) -> str:
    return f"{in_epsg}:{out_epsg}:{round(e, _KEY_DECIMALS)}:{round(n, _KEY_DECIMALS)}"


class ConvCache:
    """A write-through cache of conversion results, persisted as JSON."""

    def __init__(self, data: dict[str, list[float]] | None = None):
        self._data: dict[str, list[float]] = data or {}
        self._dirty = False

    @classmethod
    def load(cls) -> "ConvCache":
        try:
            raw = json.loads(_conv_file().read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return cls(raw)
        except (OSError, ValueError):
            pass
        return cls()

    def get(self, in_epsg: int, out_epsg: int, e: float, n: float) -> tuple[float, float] | None:
        v = self._data.get(_conv_key(in_epsg, out_epsg, e, n))
        if v and len(v) == 2:
            return (v[0], v[1])
        return None

    def put(self, in_epsg: int, out_epsg: int, e: float, n: float, result: tuple[float, float]) -> None:
        self._data[_conv_key(in_epsg, out_epsg, e, n)] = [result[0], result[1]]
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            _conv_file().write_text(
                json.dumps(self._data, ensure_ascii=False), encoding="utf-8"
            )
            self._dirty = False
        except OSError:
            pass

    def __len__(self) -> int:
        return len(self._data)


def stats() -> dict:
    """Return cache statistics for the ``cache --stats`` command."""
    conv = _conv_file()
    syst = _systems_file()
    return {
        "cache_dir": str(cache_dir()),
        "systems_cached": len(load_systems()),
        "conversions_cached": len(ConvCache.load()),
        "conversions_file": str(conv) if conv.exists() else None,
        "size_bytes": (conv.stat().st_size if conv.exists() else 0)
        + (syst.stat().st_size if syst.exists() else 0),
    }


def clear() -> list[str]:
    """Delete cache files. Returns the paths removed."""
    removed = []
    for f in (_conv_file(), _systems_file()):
        if f.exists():
            try:
                f.unlink()
                removed.append(str(f))
            except OSError:
                pass
    return removed
