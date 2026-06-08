"""openverto — Python CLI and library for the IGM Verto Online coordinate service.

Convert coordinates between every Italian reference system (Roma40, ED50,
IGM95, ETRS89, RDN2008) via the official IGM service, with zero grid-file
setup. Offline EPSG intelligence (``inspect``, ``targets``, ``detect``) needs
no network.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("openverto")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .base import (
    MAX_COORD,
    VertoError,
    get_extra_headers,
    set_base_url,
    set_extra_headers,
    set_throttle,
    set_timeout,
)
from .transform import convert, convert_skipping, inspect, roundtrip, targets
from .detect import detect
from .geo import read_csv_file, reproject_geojson, resolve_column, rows_to_geojson
from .systems import info, system_by_epsg, systems

__all__ = [
    "systems",
    "system_by_epsg",
    "info",
    "convert",
    "convert_skipping",
    "inspect",
    "targets",
    "roundtrip",
    "detect",
    "reproject_geojson",
    "read_csv_file",
    "resolve_column",
    "rows_to_geojson",
    "set_timeout",
    "set_throttle",
    "set_base_url",
    "set_extra_headers",
    "get_extra_headers",
    "VertoError",
    "MAX_COORD",
    "__version__",
    "main",
]


def main() -> None:
    """CLI entrypoint (lazy import so the library has no CLI-only deps cost)."""
    from .cli import app

    app()
