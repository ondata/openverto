"""Offline tests: static reference data, the detect heuristic, and GeoJSON
walking — no network. Values are pinned against the Go source they were ported
from."""

from __future__ import annotations

import openverto as ov
from openverto.detect import classify_coord
from openverto.geo import reproject_geojson
from openverto.refdata import REF_TABLE, datum_family


def test_reftable_has_20_systems():
    assert len(REF_TABLE) == 20


def test_inspect_3003_gauss_boaga_west():
    card = ov.inspect(3003, with_live=False)
    assert card["datum_family"] == "Roma40 / Monte Mario"
    assert card["kind"] == "projected"
    assert card["unit"] == "metre"
    assert "Ovest" in card["zone"]


def test_targets_excludes_same_datum():
    rows = ov.targets(3003, with_live=False)
    families = {r["datum_family"] for r in rows}
    # No Roma40 destination (same datum is rejected by the service).
    assert "Roma40 / Monte Mario" not in families
    assert len(rows) == 16  # 20 total minus the 4 Roma40 systems


def test_inspect_unknown_epsg_raises():
    import pytest

    with pytest.raises(KeyError):
        ov.inspect(99999, with_live=False)


def test_detect_geographic_in_italy():
    d = classify_coord(12.4924, 41.8902)
    assert d["kind"] == "geographic"
    assert d["plausibly_in_italy"] is True
    assert 4265 in d["candidate_epsg"]


def test_detect_geographic_outside_italy():
    d = classify_coord(2.35, 48.85)  # Paris
    assert d["kind"] == "geographic"
    assert d["plausibly_in_italy"] is False
    assert "outside Italy" in d["note"]


def test_detect_gauss_boaga_east():
    d = classify_coord(2300000, 4640000)
    assert d["kind"] == "projected"
    assert d["candidate_epsg"] == [3004]
    assert d["confidence"] == "medium"


def test_detect_gauss_boaga_west():
    d = classify_coord(1500000, 4640000)
    assert d["candidate_epsg"] == [3003]


def test_detect_unknown():
    d = classify_coord(99, 99)  # n>90 but small e: not geographic, not Italian projected
    assert d["kind"] == "unknown"


def test_datum_family():
    assert datum_family(6706) == "RDN2008 (ETRF2000)"
    assert datum_family(0) == ""


def test_geojson_walk_handles_integer_positions():
    """JSON gives int for integer-valued positions; the walker must not skip them."""
    doc = {"type": "Point", "coordinates": [12, 42]}  # ints, not floats
    captured = {}

    def fake_convert(coords, a, b, use_cache=True):
        captured["coords"] = coords
        return [(c[0] + 1, c[1] + 1) for c in coords]

    out = reproject_geojson(doc, 4265, 6706, converter=fake_convert)
    assert captured["coords"] == [(12.0, 42.0)]
    assert out["coordinates"] == [13.0, 43.0]
    assert out["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::6706"
