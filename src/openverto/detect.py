"""Offline magnitude heuristic to guess a coordinate's source reference system.

This is a pure offline classifier by design: it guesses the likely source
system from the ranges of a coordinate's e/n values, with no API call. It is a
HINT, not an authority — easting magnitudes overlap across systems — so it
returns candidates plus a confidence.

Ported verbatim from the Go ``detect.go`` ``classifyCoord``.
"""

from __future__ import annotations

from .refdata import ref_by_epsg

__all__ = ["detect"]


def detect(e: float, n: float) -> dict:
    """Guess the likely source reference system of an ``(e, n)`` coordinate."""
    res = classify_coord(e, n)
    names = []
    for c in res["candidate_epsg"]:
        ref = ref_by_epsg(c)
        if ref:
            names.append(f"{c} {ref['name']}")
    res["candidate_names"] = names
    return res


def classify_coord(e: float, n: float) -> dict:
    """Apply grounded magnitude heuristics (calibrated against live IGM
    conversions of Rome and Milan reference points) to guess the system."""
    res = {
        "e": e,
        "n": n,
        "kind": "",
        "confidence": "low",
        "candidate_epsg": [],
        "reason": "",
        "note": "",
        "plausibly_in_italy": False,
    }
    ae, an = abs(e), abs(n)

    # Geographic: decimal degrees.
    if ae <= 180 and an <= 90:
        res["kind"] = "geographic"
        res["plausibly_in_italy"] = 5.5 <= e <= 19.5 and 35 <= n <= 48
        res["candidate_epsg"] = [4265, 4806, 4230, 4670, 6706]
        res["reason"] = "both values are within degree range (|e|<=180, |n|<=90)"
        res["note"] = (
            "Geographic systems differ only by datum; values alone cannot tell "
            "Roma40 from ED50/IGM95/RDN2008. Confirm the datum from the dataset's metadata."
        )
        if not res["plausibly_in_italy"]:
            res["note"] = (
                "Coordinate is outside Italy's geographic bounds; the IGM grid will reject it. "
                + res["note"]
            )
        return res

    res["kind"] = "projected"
    # Projected northing for Italian UTM/TM/Gauss-Boaga is ~3.9M–5.3M; LAEA/LCC
    # use a very different northing (~1.5M–3.5M).
    italy_northing = 3_900_000 <= an <= 5_300_000
    res["plausibly_in_italy"] = italy_northing or (
        3_800_000 <= ae <= 4_700_000 and 1_500_000 <= an <= 3_500_000
    )

    if 100_000 <= ae <= 950_000 and italy_northing:
        res["candidate_epsg"] = [23032, 23033, 23034, 3064, 3065, 9716, 6707, 6708, 6709]
        res["reason"] = (
            "easting ~0.1–0.95M with northing ~3.9–5.3M: UTM/TM zone (32/33/34) "
            "on ED50, IGM95 or RDN2008"
        )
        res["note"] = (
            "Easting cannot distinguish the UTM zone (each zone resets near 500 000) "
            "nor the datum. Use the dataset's stated zone/datum, or inspect a candidate."
        )
    elif 1_200_000 <= ae < 2_000_000 and italy_northing:
        res["candidate_epsg"] = [3003]
        res["confidence"] = "medium"
        res["reason"] = (
            "easting ~1.2–2.0M with Italian northing: Gauss-Boaga fuso Ovest "
            "(Monte Mario / Italy zone 1)"
        )
    elif 2_000_000 <= ae < 2_700_000 and italy_northing:
        res["candidate_epsg"] = [3004]
        res["confidence"] = "medium"
        res["reason"] = (
            "easting ~2.0–2.7M with Italian northing: Gauss-Boaga fuso Est "
            "(Monte Mario / Italy zone 2)"
        )
    elif 2_700_000 <= ae < 3_200_000 and italy_northing:
        res["candidate_epsg"] = [6876, 3004]
        res["reason"] = (
            "easting ~2.7–3.2M: RDN2008 Zone 12 (also overlaps Gauss-Boaga fuso Est)"
        )
    elif 3_800_000 <= ae <= 4_700_000 and 1_500_000 <= an <= 3_500_000:
        res["candidate_epsg"] = [3035, 3034]
        res["confidence"] = "medium"
        res["reason"] = (
            "easting ~3.8–4.7M with low northing ~1.5–3.5M: ETRS89 LAEA or LCC "
            "(pan-European grid)"
        )
    elif 6_500_000 <= ae <= 7_200_000 and italy_northing:
        res["candidate_epsg"] = [7794]
        res["confidence"] = "medium"
        res["reason"] = "easting ~6.5–7.2M: RDN2008 Italy Zone (E-N), single national zone"
    else:
        res["kind"] = "unknown"
        res["reason"] = (
            "the e/n magnitudes do not match any known Italian projected range; "
            "the coordinate may be in a non-Italian system or have swapped axes"
        )
        res["note"] = "Try swapping e and n, or check the dataset's stated CRS."

    res["candidate_epsg"] = sorted(res["candidate_epsg"])
    if not res["note"]:
        res["note"] = "Heuristic only — confirm with 'openverto inspect <epsg>'."
    return res
