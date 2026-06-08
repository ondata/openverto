"""Coordinate conversion (``conversione``) plus EPSG intelligence.

Coordinates are passed and returned as ``(e, n)`` tuples, where ``e`` is est
(easting OR longitude) and ``n`` is nord (northing OR latitude). Geographic
coordinates are ALWAYS decimal degrees.
"""

from __future__ import annotations

import math
import time
from typing import Iterable, Sequence

from . import cache
from .base import MAX_COORD, VertoError, get_throttle, post
from .refdata import REF_TABLE, datum_family, ref_by_epsg
from .systems import system_by_epsg, systems

Coord = tuple[float, float]

__all__ = [
    "convert",
    "convert_skipping",
    "inspect",
    "targets",
    "roundtrip",
    "MAX_COORD",
]


def _to_pairs(coords: Iterable) -> list[Coord]:
    out: list[Coord] = []
    for c in coords:
        if isinstance(c, dict):
            out.append((float(c["e"]), float(c["n"])))
        else:
            e, n = c
            out.append((float(e), float(n)))
    return out


def _convert_chunk(in_epsg: int, out_epsg: int, coords: Sequence[Coord]) -> list[Coord]:
    """Convert a single chunk (<= MAX_COORD coordinates) in one request."""
    body = {
        "richiesta": "conversione",
        "utente": "openverto",
        "chiave": "openverto",
        "inEpsg": in_epsg,
        "outEpsg": out_epsg,
        "coordinate": [{"e": e, "n": n} for e, n in coords],
    }
    resp = post(body)
    if resp.get("stato") != "successo":
        raise VertoError(resp.get("messaggio", "unknown error"), resp.get("dove", ""))
    out = resp.get("coordinate", [])
    if len(out) != len(coords):
        raise ValueError(
            f"service returned {len(out)} coordinates for {len(coords)} input"
        )
    return [(float(c["e"]), float(c["n"])) for c in out]


def convert(
    coords: Iterable,
    from_epsg: int,
    to_epsg: int,
    *,
    use_cache: bool = True,
) -> list[Coord]:
    """Convert coordinates from ``from_epsg`` to ``to_epsg``.

    Input is auto-split into chunks of at most ``MAX_COORD``. Output preserves
    input order. Cache hits avoid the network entirely. A single out-of-grid
    coordinate fails its whole chunk (the service is all-or-nothing per
    request); use :func:`convert_skipping` to isolate and skip offenders.

    Raises :class:`~openverto.base.VertoError` on a service-level rejection.
    """
    pairs = _to_pairs(coords)
    if not pairs:
        return []

    results: list[Coord | None] = [None] * len(pairs)
    conv_cache = cache.ConvCache.load() if use_cache else None

    miss_idx: list[int] = []
    miss: list[Coord] = []
    for i, (e, n) in enumerate(pairs):
        if conv_cache is not None:
            hit = conv_cache.get(from_epsg, to_epsg, e, n)
            if hit is not None:
                results[i] = hit
                continue
        miss_idx.append(i)
        miss.append((e, n))

    multibatch = len(miss) > MAX_COORD
    for k, start in enumerate(range(0, len(miss), MAX_COORD)):
        if multibatch and k > 0 and get_throttle() > 0:
            time.sleep(get_throttle())  # be kind to the free IGM service
        chunk = miss[start : start + MAX_COORD]
        got = _convert_chunk(from_epsg, to_epsg, chunk)
        for j, res in enumerate(got):
            idx = miss_idx[start + j]
            results[idx] = res
            if conv_cache is not None:
                conv_cache.put(from_epsg, to_epsg, *miss[start + j], res)

    if conv_cache is not None:
        conv_cache.save()
    return [r for r in results]  # type: ignore[misc]


def convert_skipping(
    coords: Iterable,
    from_epsg: int,
    to_epsg: int,
) -> tuple[list[Coord | None], list[int]]:
    """Convert coordinates, isolating and skipping any the service rejects.

    Bisects failing chunks down to the single offending coordinate. Returns a
    ``(results, skipped)`` pair: ``results`` is the same length as the input,
    with ``None`` at skipped positions; ``skipped`` is the list of skipped
    indices. Non-service errors (network) propagate.
    """
    pairs = _to_pairs(coords)
    results: list[Coord | None] = [None] * len(pairs)
    skipped: list[int] = []
    # Throttle only multi-batch jobs (> MAX_COORD); a single batch is never delayed.
    gate = {"throttle": get_throttle() if len(pairs) > MAX_COORD else 0.0, "first": True}
    _convert_range(from_epsg, to_epsg, pairs, 0, results, skipped, gate)
    return results, skipped


def _convert_range(in_epsg, out_epsg, sub, offset, results, skipped, gate) -> None:
    if not sub:
        return
    if len(sub) > MAX_COORD:
        mid = len(sub) // 2
        _convert_range(in_epsg, out_epsg, sub[:mid], offset, results, skipped, gate)
        _convert_range(in_epsg, out_epsg, sub[mid:], offset + mid, results, skipped, gate)
        return
    if gate["throttle"] and not gate["first"]:
        time.sleep(gate["throttle"])  # be kind to the free IGM service
    gate["first"] = False
    try:
        got = _convert_chunk(in_epsg, out_epsg, sub)
    except VertoError:
        if len(sub) == 1:
            skipped.append(offset)
            return
        mid = len(sub) // 2
        _convert_range(in_epsg, out_epsg, sub[:mid], offset, results, skipped, gate)
        _convert_range(in_epsg, out_epsg, sub[mid:], offset + mid, results, skipped, gate)
        return
    for j, res in enumerate(got):
        results[offset + j] = res


def inspect(epsg: int, *, with_live: bool = True) -> dict:
    """Return resolved metadata for an EPSG: datum family, axis order, units,
    zone and false easting, joined with the live IGM description when available.

    Raises :class:`KeyError` if the EPSG is not IGM-supported.
    """
    ref = ref_by_epsg(epsg)
    if ref is None:
        raise KeyError(epsg)
    desc = ref["name"]
    if with_live:
        try:
            s = system_by_epsg(systems(), epsg)
            if s and s.get("descrizione"):
                desc = s["descrizione"].strip()
        except Exception:
            pass
    axis = "e=est/longitude, n=nord/latitude (decimal degrees)"
    if ref["kind"] == "projected":
        axis = "e=easting (m), n=northing (m)"
    card = {
        "epsg": epsg,
        "description": desc,
        "name": ref["name"],
        "datum_family": ref["datum_family"],
        "kind": ref["kind"],
        "unit": ref["unit"],
        "axis_order": axis,
        "notes": ref["notes"],
    }
    if ref["zone"]:
        card["zone"] = ref["zone"]
    if ref["false_easting"]:
        card["false_easting"] = ref["false_easting"]
    return card


def targets(epsg: int, *, with_live: bool = True) -> list[dict]:
    """List valid conversion destinations for a source EPSG.

    The service rejects conversions between systems that share the same datum,
    so only systems in a different datum family are returned.

    Raises :class:`KeyError` if the EPSG is not IGM-supported.
    """
    src_family = datum_family(epsg)
    if not src_family:
        raise KeyError(epsg)
    live: list[dict] = []
    if with_live:
        try:
            live = systems()
        except Exception:
            live = []
    rows = []
    for code, ref in REF_TABLE.items():
        if ref["datum_family"] == src_family:
            continue
        desc = ref["name"]
        s = system_by_epsg(live, code)
        if s and s.get("descrizione"):
            desc = s["descrizione"].strip()
        rows.append(
            {
                "epsg": code,
                "description": desc,
                "datum_family": ref["datum_family"],
                "kind": ref["kind"],
            }
        )
    rows.sort(key=lambda r: r["epsg"])
    return rows


def _residual_metres(in_coord: Coord, de: float, dn: float, unit: str) -> float:
    if unit == "degree":
        lat_rad = in_coord[1] * math.pi / 180
        dx = de * 111320.0 * math.cos(lat_rad)
        dy = dn * 110540.0
        return math.hypot(dx, dy)
    return math.hypot(de, dn)


def roundtrip(
    coords: Iterable,
    from_epsg: int,
    to_epsg: int,
    *,
    use_cache: bool = True,
) -> dict:
    """Convert each coordinate A->B->A and report the residual error.

    Returns a report dict with per-point residuals (Δe, Δn, distance in metres)
    and the max/mean residual distance — used to certify a datum chain is
    lossless within tolerance.
    """
    pairs = _to_pairs(coords)
    forward = convert(pairs, from_epsg, to_epsg, use_cache=use_cache)
    back = convert(forward, to_epsg, from_epsg, use_cache=use_cache)

    unit = "metre"
    ref = ref_by_epsg(from_epsg)
    if ref and ref["kind"] == "geographic":
        unit = "degree"

    rows = []
    total = 0.0
    max_resid = 0.0
    for i, (e, n) in enumerate(pairs):
        de = back[i][0] - e
        dn = back[i][1] - n
        dm = _residual_metres((e, n), de, dn, unit)
        rows.append(
            {
                "in_e": e,
                "in_n": n,
                "back_e": back[i][0],
                "back_n": back[i][1],
                "residual_e": abs(de),
                "residual_n": abs(dn),
                "residual_m": dm,
            }
        )
        total += dm
        max_resid = max(max_resid, dm)
    return {
        "from_epsg": from_epsg,
        "to_epsg": to_epsg,
        "source_unit": unit,
        "points": rows,
        "max_residual_m": max_resid,
        "mean_residual_m": total / len(rows) if rows else 0.0,
    }
