"""GeoJSON reprojection and CSV batch helpers."""

from __future__ import annotations

import csv
from typing import Callable

from .transform import Coord, convert

__all__ = [
    "reproject_geojson",
    "read_csv_file",
    "resolve_column",
    "rows_to_geojson",
    "E_ALIASES",
    "N_ALIASES",
]

E_ALIASES = ["e", "est", "easting", "lon", "long", "longitude", "x"]
N_ALIASES = ["n", "nord", "northing", "lat", "latitude", "y"]


def _is_number(x) -> bool:
    # bool is a subclass of int; exclude it. JSON ints (e.g. 16) must count.
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _collect_positions(node, positions: list, setters: list) -> None:
    """Walk a decoded GeoJSON value, recording every innermost position and a
    setter that writes the converted x/y back in place."""
    if isinstance(node, dict):
        for k, child in node.items():
            if k == "coordinates":
                _walk_coordinates(child, positions, setters)
            else:
                _collect_positions(child, positions, setters)
    elif isinstance(node, list):
        for child in node:
            _collect_positions(child, positions, setters)


def _walk_coordinates(node, positions: list, setters: list) -> None:
    if not isinstance(node, list) or not node:
        return
    if len(node) >= 2 and _is_number(node[0]) and _is_number(node[1]):
        positions.append((float(node[0]), float(node[1])))
        arr = node  # captured by reference; mutated in place below

        def _set(c: Coord, arr=arr) -> None:
            arr[0] = c[0]
            arr[1] = c[1]

        setters.append(_set)
        return
    for child in node:
        _walk_coordinates(child, positions, setters)


def _set_crs(doc, epsg: int):
    if isinstance(doc, dict):
        doc["crs"] = {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"},
        }
    return doc


def reproject_geojson(
    doc,
    from_epsg: int,
    to_epsg: int,
    *,
    converter: Callable[[list, int, int], list] = convert,
    use_cache: bool = True,
):
    """Reproject every geometry position in a decoded GeoJSON document.

    Mutates and returns ``doc``. A top-level CRS member naming the target EPSG
    is added. Raises ``ValueError`` if no coordinates are found.
    """
    positions: list[Coord] = []
    setters: list[Callable] = []
    _collect_positions(doc, positions, setters)
    if not positions:
        raise ValueError("no coordinates found in the GeoJSON document")
    try:
        converted = converter(positions, from_epsg, to_epsg, use_cache=use_cache)
    except TypeError:
        converted = converter(positions, from_epsg, to_epsg)
    for setter, c in zip(setters, converted):
        setter(c)
    return _set_crs(doc, to_epsg)


def read_csv_file(path: str) -> tuple[list[str], list[list[str]]]:
    """Read a CSV file, returning ``(header, records)``."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError("empty CSV file")
    return rows[0], rows[1:]


def resolve_column(header: list[str], explicit: str, aliases: list[str]) -> int:
    """Find a column index by explicit name (case-insensitive) or alias."""
    def find(name: str) -> int:
        for i, h in enumerate(header):
            if h.strip().lower() == name.strip().lower():
                return i
        return -1

    if explicit and explicit.strip():
        idx = find(explicit)
        if idx >= 0:
            return idx
        raise ValueError(
            f"column {explicit!r} not found; available: {', '.join(header)}"
        )
    for a in aliases:
        idx = find(a)
        if idx >= 0:
            return idx
    raise ValueError(
        f"could not auto-detect a column (tried {', '.join(aliases)}); "
        f"pass an explicit column. Available: {', '.join(header)}"
    )


def rows_to_geojson(
    header: list[str],
    records: list[list[str]],
    converted: list,
    skipped: set[int],
    out_epsg: int,
) -> dict:
    """Build a GeoJSON FeatureCollection of points from converted CSV rows."""
    features = []
    for i, rec in enumerate(records):
        if i in skipped:
            continue
        props = {header[j]: rec[j] for j in range(len(header)) if j < len(rec)}
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [converted[i][0], converted[i][1]],
                },
                "properties": props,
            }
        )
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{out_epsg}"},
        },
        "features": features,
    }
