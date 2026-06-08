"""GeoJSON reprojection and CSV batch helpers."""

from __future__ import annotations

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


_DELIM_CANDIDATES = [",", ";", "\t", "|"]


def _detect_delimiter(header_line: str, decimal: str) -> str:
    """Pick the delimiter by counting candidates in the header line.

    Column names rarely contain the delimiter, so the header is a reliable
    signal. When the decimal separator is a comma, comma cannot be the
    delimiter, so it is excluded — this is exactly the case DuckDB's own sniffer
    gets wrong on all-numeric rows.
    """
    candidates = [d for d in _DELIM_CANDIDATES if not (decimal == "," and d == ",")]
    counts = {d: header_line.count(d) for d in candidates}
    best = max(counts, key=lambda d: counts[d])
    if counts[best] == 0:
        return ";" if decimal == "," else ","
    return best


def read_csv_file(path: str, *, decimal: str = ".") -> tuple[list[str], list[list[str]]]:
    """Read a CSV via DuckDB, returning ``(header, records)`` as raw strings.

    The delimiter (``,``, ``;``, tab, ``|``) is detected from the header line;
    ``decimal`` is used only to exclude the comma as a delimiter candidate when
    it is the decimal separator. Every cell is kept as its **original string**
    (``read_csv`` with ``all_varchar``), so attribute columns like ``19.90`` or
    ``1000,50`` are never reformatted — the caller normalises the decimal of the
    coordinate columns only. NULL/empty cells become ``""``. ``path`` may be
    ``-`` to read from standard input.
    """
    if decimal not in (".", ","):
        raise ValueError(f"decimal separator must be '.' or ',', got {decimal!r}")
    import os
    import sys
    import tempfile

    import duckdb

    tmp = None
    if path == "-":
        fd, tmp = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(sys.stdin.read())
        real = tmp
    else:
        real = path
    try:
        with open(real, encoding="utf-8-sig") as f:
            first_line = f.readline()
        if not first_line:
            raise ValueError("empty CSV file")
        delim = _detect_delimiter(first_line, decimal)
        con = duckdb.connect()
        try:
            rel = con.execute(
                "SELECT * FROM read_csv(?, header=true, delim=?, all_varchar=true)",
                [real, delim],
            )
            header = [d[0] for d in rel.description]
            rows = rel.fetchall()
        except duckdb.Error as exc:
            raise ValueError(f"could not read CSV: {exc}") from exc
        finally:
            con.close()
    finally:
        if tmp:
            os.unlink(tmp)
    records = [["" if v is None else str(v) for v in row] for row in rows]
    return header, records


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
