"""Build horizontal shift grids from the IGM Verto Online service.

A regular lattice of nodes in the source datum is converted through the service
and the shift is taken by difference, then written as a PROJ GeoTIFF grid
(https://proj.org/en/stable/specifications/geodetictiffgrids.html).

The service is free and shared, so this module never bisects, never runs in
parallel and caches every successful batch. One coordinate outside the IGM
coverage fails its whole request, and the service does not say which one:
isolating it would cost at least one request per rejected node. The grid must
therefore be a rectangle fully inside the coverage, which also suits PROJ: it
interpolates nodata values as if they were numbers.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import time
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import httpx

from . import cache as cache_mod
from .base import MAX_COORD, USER_AGENT_VERSION, VertoError
from .refdata import RETIRED_EPSG, datum_family, ref_by_epsg, retired_message
from .transform import Coord, _convert_chunk

#: Default lattice step of the IGM grids: 7.5' in longitude, 5' in latitude.
DEFAULT_STEP_LON = 450.0
DEFAULT_STEP_LAT = 300.0
#: Above this many requests the caller has to confirm explicitly.
CONFIRM_THRESHOLD = 10
DEFAULT_PAUSE = 2.0
MAX_CONSECUTIVE_ERRORS = 3
#: First backoff, in seconds; doubles at every consecutive error.
BACKOFF = 2.0

#: Where the IGM grid nodes fall, read from an official NTv2 file: multiples of
#: 7.5' from the Monte Mario meridian and of 5' in latitude. Sampling off these
#: nodes costs up to 4 cm between them, on nodes it matches the service to 1 mm.
IGM_ORIGIN_LON = 12 + 27 / 60 + 8.4 / 3600
IGM_ORIGIN_LAT = 44.0

_ARCSEC_TOLERANCE = 1e-6
#: The longitudes of this system are referred to the Rome meridian.
_ROME_MERIDIAN_EPSG = 4806


class GridError(ValueError):
    """The requested grid cannot be built as specified."""


@dataclass(frozen=True)
class Lattice:
    """A regular lattice; steps are arc-seconds, ``west``/``south`` degrees."""

    west: float
    south: float
    step_lon: float
    step_lat: float
    nx: int
    ny: int

    def lon(self, i: int) -> float:
        return round(self.west + i * self.step_lon / 3600, 10)

    def lat(self, j: int) -> float:
        return round(self.south + j * self.step_lat / 3600, 10)

    @property
    def size(self) -> int:
        return self.nx * self.ny

    def nodes(self) -> list[Coord]:
        """Every node, west to east and south to north."""
        return [(self.lon(i), self.lat(j)) for j in range(self.ny) for i in range(self.nx)]


def _axis(low: float, high: float, step: float, origin: float | None) -> tuple[float, int]:
    """Return the first node and the node count of one axis inside [low, high]."""
    origin = low if origin is None else origin
    first = math.ceil((low - origin) * 3600 / step - _ARCSEC_TOLERANCE)
    start = origin + first * step / 3600
    return start, math.floor((high - start) * 3600 / step + _ARCSEC_TOLERANCE) + 1


def build_lattice(
    bbox: Sequence[float],
    *,
    step_lon: float = DEFAULT_STEP_LON,
    step_lat: float = DEFAULT_STEP_LAT,
    origin_lon: float | None = None,
    origin_lat: float | None = None,
) -> Lattice:
    """Build the lattice of nodes inside ``bbox`` (west, south, east, north).

    Nodes never fall outside the bbox: with a step that does not divide it, the
    lattice stops at the last node inside. With the IGM step and no explicit
    origin the nodes are those of the IGM grids; otherwise the bbox corner.
    """
    west, south, east, north = bbox
    if not (west < east and south < north):
        raise GridError("--bbox must be west south east north, with west < east and south < north")
    if step_lon <= 0 or step_lat <= 0:
        raise GridError("--step-lon and --step-lat must be positive")
    if origin_lon is None and step_lon == DEFAULT_STEP_LON:
        origin_lon = IGM_ORIGIN_LON
    if origin_lat is None and step_lat == DEFAULT_STEP_LAT:
        origin_lat = IGM_ORIGIN_LAT
    start_lon, nx = _axis(west, east, step_lon, origin_lon)
    start_lat, ny = _axis(south, north, step_lat, origin_lat)
    if nx < 2 or ny < 2:
        raise GridError(f"the lattice has {nx} x {ny} nodes: at least 2 x 2 are needed to interpolate")
    return Lattice(start_lon, start_lat, step_lon, step_lat, nx, ny)


def check_systems(from_epsg: int, to_epsg: int) -> None:
    """Accept only pairs of geographic systems the service can convert."""
    for epsg in (from_epsg, to_epsg):
        if epsg in RETIRED_EPSG:
            raise GridError(retired_message(epsg))
        ref = ref_by_epsg(epsg)
        if ref is None:
            raise GridError(f"EPSG {epsg} is not IGM-supported; run 'openverto systems'")
        if ref["kind"] != "geographic":
            raise GridError(f"EPSG {epsg} is projected: a grid needs geographic systems (4265, 4230, 4670, 6706)")
        if epsg == _ROME_MERIDIAN_EPSG:
            raise GridError("EPSG 4806 has longitudes from the Rome meridian: use 4265")
    if datum_family(from_epsg) == datum_family(to_epsg):
        raise GridError(f"EPSG {from_epsg} and {to_epsg} share the same datum: there is no shift to grid")


def _batches(nodes: list[Coord], max_coord: int) -> list[list[Coord]]:
    return [nodes[i : i + max_coord] for i in range(0, len(nodes), max_coord)]


def _key(from_epsg: int, to_epsg: int, batch: list[Coord]) -> str:
    raw = json.dumps([from_epsg, to_epsg, batch], separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class _BatchCache:
    """One file per successful batch: a resumed run replays them for free."""

    def __init__(self, directory: str | Path | None):
        self.dir = Path(directory) if directory else cache_mod.cache_dir() / "grid"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def get(self, key: str) -> list[Coord] | None:
        try:
            return [(float(e), float(n)) for e, n in json.loads(self._path(key).read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            return None

    def put(self, key: str, coords: list[Coord]) -> None:
        _write_atomic(self._path(key), json.dumps(coords).encode())


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def plan_grid(
    lattice: Lattice,
    from_epsg: int,
    to_epsg: int,
    *,
    max_coord: int = MAX_COORD,
    pause: float = DEFAULT_PAUSE,
    cache_dir: str | Path | None = None,
) -> dict:
    """Describe the work to do, without touching the network."""
    cache = _BatchCache(cache_dir)
    batches = _batches(lattice.nodes(), max_coord)
    cached = sum(cache.has(_key(from_epsg, to_epsg, b)) for b in batches)
    requests = len(batches) - cached
    return {
        "nodes": lattice.size,
        "nx": lattice.nx,
        "ny": lattice.ny,
        "max_coord": max_coord,
        "batches": len(batches),
        "cached_batches": cached,
        "requests": requests,
        "estimated_seconds": requests + max(requests - 1, 0) * pause,
    }


def _fetch(
    batches: list[list[Coord]],
    from_epsg: int,
    to_epsg: int,
    cache: _BatchCache,
    report: dict,
    pause: float,
    sleep: Callable[[float], None],
) -> list[Coord]:
    """Convert the batches one at a time, skipping those already cached."""
    results: list[Coord] = []
    consecutive = 0
    sent = 0
    for batch in batches:
        key = _key(from_epsg, to_epsg, batch)
        got = cache.get(key)
        if got is not None:
            report["cached_batches"] += 1
        while got is None:
            if sent:
                sleep(pause)
            sent += 1
            report["requests"] += 1
            try:
                got = _convert_chunk(from_epsg, to_epsg, batch, retries=0)
            except (httpx.TransportError, httpx.HTTPStatusError):
                consecutive += 1
                if consecutive >= MAX_CONSECUTIVE_ERRORS:
                    raise
                sleep(BACKOFF * 2 ** (consecutive - 1))
                continue
            consecutive = 0
            cache.put(key, got)
        results.extend(got)
        report["nodes_valid"] = len(results)
        report["nodes_error"] = report["nodes_total"] - len(results)
    return results


def build_grid(
    lattice: Lattice,
    from_epsg: int,
    to_epsg: int,
    out: str | Path,
    *,
    max_coord: int = MAX_COORD,
    pause: float = DEFAULT_PAUSE,
    cache_dir: str | Path | None = None,
    info_requests: int = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Build the grid and write ``out`` plus ``<out>.report.json``; return the report.

    Writes no grid unless every node is converted. On failure the report still
    records what happened, and the exception propagates.
    """
    out = Path(out)
    report: dict = {
        "status": "error",
        "error": None,
        "grid": None,
        "report": f"{out}.report.json",
        "from_epsg": from_epsg,
        "to_epsg": to_epsg,
        "nodes_total": lattice.size,
        "nodes_valid": 0,
        "nodes_error": lattice.size,
        "requests": info_requests,
        "cached_batches": 0,
    }
    try:
        nodes = lattice.nodes()
        batches = _batches(nodes, max_coord)
        converted = _fetch(batches, from_epsg, to_epsg, _BatchCache(cache_dir), report, pause, sleep)
        write_gtiff(out, lattice, nodes, converted, from_epsg, to_epsg)
        report["status"] = "ok"
        report["grid"] = str(out)
    except (VertoError, httpx.HTTPError, ValueError, OSError) as exc:
        report["error"] = str(exc)
        raise
    finally:
        _write_atomic(Path(report["report"]), json.dumps(report, indent=2).encode())
    return report


def _gdal_metadata(lattice: Lattice, from_epsg: int, to_epsg: int) -> bytes:
    def item(name: str, value, attrs: str = "") -> str:
        return f'<Item name="{name}"{attrs}>{escape(str(value))}</Item>'

    items = [
        item("TYPE", "HORIZONTAL_OFFSET"),
        item("DESCRIPTION", "latitude_offset", ' sample="0" role="description"'),
        item("DESCRIPTION", "longitude_offset", ' sample="1" role="description"'),
        item("UNITTYPE", "arc-second", ' sample="0" role="unittype"'),
        item("UNITTYPE", "arc-second", ' sample="1" role="unittype"'),
        item("positive_value", "east", ' sample="1"'),
        item("source_crs_epsg_code", from_epsg),
        item("target_crs_epsg_code", to_epsg),
        item("grid_name", f"openverto_{from_epsg}_{to_epsg}"),
        item("source", "IGM Verto Online"),
        item("software", USER_AGENT_VERSION),
        item("step_lon_arcsec", lattice.step_lon),
        item("step_lat_arcsec", lattice.step_lat),
        item("origin_lon", lattice.lon(0)),
        item("origin_lat", lattice.lat(0)),
    ]
    return ("<GDALMetadata>" + "".join(items) + "</GDALMetadata>").encode() + b"\0"


def _ifd_value(typ: int, values: Sequence) -> bytes:
    return struct.pack(f"<{len(values)}{ {3: 'H', 4: 'I', 12: 'd'}[typ] }", *values)


def write_gtiff(
    out: str | Path,
    lattice: Lattice,
    nodes: Sequence[Coord],
    converted: Sequence[Coord],
    from_epsg: int,
    to_epsg: int,
    *,
    when: datetime | None = None,
) -> None:
    """Write a PROJ GeoTIFF horizontal shift grid (Float32, arc-seconds, east positive)."""
    nx, ny = lattice.nx, lattice.ny
    dlat = [(c[1] - n[1]) * 3600 for n, c in zip(nodes, converted)]
    dlon = [(c[0] - n[0]) * 3600 for n, c in zip(nodes, converted)]

    def strip(values: list[float]) -> bytes:
        # TIFF rows run north to south, the lattice south to north.
        raw = b"".join(struct.pack(f"<{nx}f", *values[j * nx : (j + 1) * nx]) for j in range(ny - 1, -1, -1))
        return zlib.compress(raw, 9)

    strips = [strip(dlat), strip(dlon)]
    pos = 8
    offsets = []
    for s in strips:
        offsets.append(pos)
        pos += len(s)
    pos += pos % 2

    stamp = (when or datetime.now(timezone.utc)).strftime("%Y:%m:%d %H:%M:%S").encode() + b"\0"
    geokeys = [1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 2, 2048, 0, 1, from_epsg]
    north = lattice.lat(ny - 1)
    entries: list[tuple[int, int, int, bytes]] = [
        (tag, typ, len(vals), _ifd_value(typ, vals))
        for tag, typ, vals in [
            (256, 4, [nx]),
            (257, 4, [ny]),
            (258, 3, [32, 32]),
            (259, 3, [8]),  # deflate
            (262, 3, [1]),  # MinIsBlack
            (273, 4, offsets),
            (277, 3, [2]),
            (278, 4, [ny]),
            (279, 4, [len(s) for s in strips]),
            (284, 3, [2]),  # one strip per band
            (338, 3, [0]),
            (339, 3, [3, 3]),  # IEEE float
            (33550, 12, [lattice.step_lon / 3600, lattice.step_lat / 3600, 0.0]),
            (33922, 12, [0.0, 0.0, 0.0, lattice.lon(0), north, 0.0]),
            (34735, 3, geokeys),
        ]
    ]
    metadata = _gdal_metadata(lattice, from_epsg, to_epsg)
    entries += [(306, 2, len(stamp), stamp), (42112, 2, len(metadata), metadata)]
    entries.sort()

    ifd_end = pos + 2 + 12 * len(entries) + 4
    ifd = struct.pack("<H", len(entries))
    extra = b""
    for tag, typ, count, payload in entries:
        if len(payload) <= 4:
            field = payload.ljust(4, b"\0")
        else:
            field = struct.pack("<I", ifd_end + len(extra))
            extra += payload + b"\0" * (len(payload) % 2)
        ifd += struct.pack("<HHI", tag, typ, count) + field
    ifd += struct.pack("<I", 0)

    data = struct.pack("<2sHI", b"II", 42, pos) + strips[0] + strips[1]
    data += b"\0" * (pos - len(data)) + ifd + extra
    _write_atomic(Path(out), data)
