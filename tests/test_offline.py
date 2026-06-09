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


def test_read_csv_semicolon_and_decimal_comma(tmp_path):
    """Italian-style CSV: ';' delimiter auto-detected; cells kept as raw strings."""
    from openverto.geo import read_csv_file

    p = tmp_path / "it.csv"
    p.write_text(
        "nome;est;nord;codice;prezzo\nroma;12,4924;41,8902;00123;1000,50\n",
        encoding="utf-8",
    )
    header, records = read_csv_file(str(p), decimal=",")
    assert header == ["nome", "est", "nord", "codice", "prezzo"]
    # cells are returned verbatim (not reformatted): comma decimals preserved,
    # leading zeros preserved, attribute trailing zeros preserved
    assert records[0] == ["roma", "12,4924", "41,8902", "00123", "1000,50"]


def test_read_csv_standard_comma_delimiter(tmp_path):
    """Standard CSV: ',' delimiter, '.' decimal — default behaviour."""
    from openverto.geo import read_csv_file

    p = tmp_path / "std.csv"
    p.write_text("nome,est,nord\nroma,12.4924,41.8902\n", encoding="utf-8")
    header, records = read_csv_file(str(p))
    assert header == ["nome", "est", "nord"]
    assert records == [["roma", "12.4924", "41.8902"]]


def test_read_csv_invalid_decimal_raises(tmp_path):
    import pytest

    from openverto.geo import read_csv_file

    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_csv_file(str(p), decimal=";")


def test_read_csv_numeric_header_decimal_comma(tmp_path):
    """Regression: an all-numeric ';' CSV with decimal comma must not be
    mis-sniffed as comma-delimited (DuckDB's own sniffer gets this wrong)."""
    from openverto.geo import read_csv_file

    p = tmp_path / "num.csv"
    p.write_text("lon;lat\n12,4924;41,8902\n", encoding="utf-8")
    header, records = read_csv_file(str(p), decimal=",")
    assert header == ["lon", "lat"]
    assert records == [["12,4924", "41,8902"]]


def test_read_csv_from_stdin(tmp_path, monkeypatch):
    import io

    from openverto.geo import read_csv_file

    monkeypatch.setattr("sys.stdin", io.StringIO("lon;lat\n12,4924;41,8902\n"))
    header, records = read_csv_file("-", decimal=",")
    assert header == ["lon", "lat"]
    assert records == [["12,4924", "41,8902"]]


def test_resolve_column_by_alias_and_missing():
    import pytest

    from openverto.geo import E_ALIASES, resolve_column

    header = ["nome", "est", "nord"]
    assert resolve_column(header, "", E_ALIASES) == 1  # 'est' alias
    assert resolve_column(header, "nord", ["n"]) == 2  # explicit name
    with pytest.raises(ValueError):
        resolve_column(header, "manca", E_ALIASES)


def test_batch_rejects_invalid_target(tmp_path):
    """batch must fail upfront when --to is not a valid target for --from."""
    from typer.testing import CliRunner

    from openverto.cli import app

    p = tmp_path / "coords.csv"
    p.write_text("lon,lat\n12.0,41.0\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["batch", str(p), "--from", "23033", "--to", "32633"])
    normalized = " ".join(result.output.split())
    assert result.exit_code != 0
    assert "32633" in normalized
    assert "23033" in normalized
    assert "targets 23033" in normalized


def test_batch_accepts_valid_target_combination(tmp_path, monkeypatch):
    """batch must pass the target check for a known-valid from/to pair."""
    import openverto.transform as convmod

    def fake_post(body):
        return {
            "stato": "successo",
            "coordinate": [{"e": c["e"] + 0.001, "n": c["n"] + 0.002} for c in body["coordinate"]],
        }

    monkeypatch.setattr(convmod, "post", fake_post)

    from typer.testing import CliRunner

    from openverto.cli import app

    p = tmp_path / "coords.csv"
    p.write_text("lon,lat\n290000.0,4640000.0\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["batch", str(p), "--from", "23033", "--to", "6706"])
    assert result.exit_code == 0
