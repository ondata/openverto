"""Offline tests: static reference data, the detect heuristic, and GeoJSON
walking — no network. Values are pinned against the Go source they were ported
from."""

from __future__ import annotations

import sys

import pytest

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


# --- base.post: tolerant parsing of a polluted response body ---------------


def _post_with_body(monkeypatch, body: str, *, status: int = 200):
    """Run base.post against a mocked transport returning ``body`` verbatim."""
    import httpx

    import openverto.base as basemod

    def handler(request):
        return httpx.Response(status, text=body, headers={"Content-Type": "application/json"})

    real_client = httpx.Client

    def fake_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(basemod.httpx, "Client", fake_client)
    return basemod.post({"richiesta": "info"}, retries=0)


def test_post_salvages_json_after_debug_prefix(monkeypatch):
    """The IGM service prefixes the conversion body with a stray SQL log line."""
    body = (
        "QUERY: INSERT INTO vol.log (email, num_vertices) VALUES ('openverto', 1)\n"
        '{\n\t"stato": "successo",\n'
        '\t"coordinate": [\n\t\t{"e": 13.3122593652, "n": 38.1163458766}\n\t]\n}\n'
    )
    resp = _post_with_body(monkeypatch, body)
    assert resp["stato"] == "successo"
    assert resp["coordinate"] == [{"e": 13.3122593652, "n": 38.1163458766}]


def test_post_salvages_json_with_trailing_junk(monkeypatch):
    resp = _post_with_body(monkeypatch, '{"stato": "successo", "coordinate": []}\nDONE\n')
    assert resp == {"stato": "successo", "coordinate": []}


def test_post_keeps_diagnostic_on_unparseable_body(monkeypatch):
    import pytest

    with pytest.raises(ValueError, match="invalid JSON from Verto service"):
        _post_with_body(monkeypatch, "<html>service unavailable</html>")


def test_post_parses_clean_body_unchanged(monkeypatch):
    """If the service stops polluting the body, the strict path still works."""
    resp = _post_with_body(monkeypatch, '{"maxCoord": 32000, "srsSupportati": []}')
    assert resp == {"maxCoord": 32000, "srsSupportati": []}


# --- credentials ------------------------------------------------------------


@pytest.fixture
def igm(monkeypatch, tmp_path):
    """Mock the IGM endpoint: returns the request bodies it received."""
    import json

    import httpx

    import openverto.base as basemod

    seen = []
    state = {"response": None}

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if state["response"] is not None:
            return state["response"]
        coords = [{"e": 1.0, "n": 2.0} for _ in body["coordinate"]]
        return httpx.Response(200, json={"stato": "successo", "coordinate": coords})

    real_client = httpx.Client
    monkeypatch.setattr(
        basemod.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setenv("OPENVERTO_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENVERTO_UTENTE", raising=False)
    monkeypatch.delenv("OPENVERTO_CHIAVE", raising=False)
    basemod.set_credentials()
    yield seen, state
    basemod.set_credentials()


def _sent(seen):
    return seen[-1]["utente"], seen[-1]["chiave"]


def test_credentials_default_placeholder(igm):
    seen, _ = igm
    ov.convert([(1, 2)], 4265, 6706, use_cache=False)
    assert _sent(seen) == ("openverto", "openverto")


def test_credentials_from_env(igm, monkeypatch):
    seen, _ = igm
    monkeypatch.setenv("OPENVERTO_UTENTE", "env@esempio.it")
    monkeypatch.setenv("OPENVERTO_CHIAVE", "ENVKEY")
    ov.convert([(1, 2)], 4265, 6706, use_cache=False)
    assert _sent(seen) == ("env@esempio.it", "ENVKEY")


def test_credentials_set_overrides_env(igm, monkeypatch):
    seen, _ = igm
    monkeypatch.setenv("OPENVERTO_UTENTE", "env@esempio.it")
    monkeypatch.setenv("OPENVERTO_CHIAVE", "ENVKEY")
    ov.set_credentials("lib@esempio.it", "LIBKEY")
    ov.convert([(1, 2)], 4265, 6706, use_cache=False)
    assert _sent(seen) == ("lib@esempio.it", "LIBKEY")


def test_cli_credential_options_override_env(igm, monkeypatch):
    from typer.testing import CliRunner

    from openverto.cli import app

    seen, _ = igm
    monkeypatch.setenv("OPENVERTO_UTENTE", "env@esempio.it")
    monkeypatch.setenv("OPENVERTO_CHIAVE", "ENVKEY")
    args = ["--utente", "cli@esempio.it", "--chiave", "CLIKEY", "convert", "--from", "4265", "--to", "6706", "--no-cache", "1", "2"]
    res = CliRunner().invoke(app, args)
    assert res.exit_code == 0, res.output
    assert _sent(seen) == ("cli@esempio.it", "CLIKEY")
    assert "CLIKEY" not in res.output


def test_key_stays_out_of_cache_files(igm, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENVERTO_CHIAVE", "SECRETKEY")
    ov.convert([(1, 2)], 4265, 6706, use_cache=True)
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files
    assert all(b"SECRETKEY" not in p.read_bytes() for p in files)


@pytest.mark.parametrize(
    "response",
    [
        {"stato": "errore", "dove": "chiave", "messaggio": "Non valida"},
        {"stato": "errore", "dove": "login", "messaggio": "Abbonamento scaduto"},
    ],
)
def test_cli_rejected_credentials_explain_what_to_do(igm, response):
    import httpx
    from typer.testing import CliRunner

    from openverto.cli import app

    _, state = igm
    state["response"] = httpx.Response(200, json=response)
    res = CliRunner().invoke(app, ["convert", "--from", "4265", "--to", "6706", "--no-cache", "1", "2"])
    assert res.exit_code == 2
    assert "Abbonamenti ai servizi" in res.output.replace("\n", " ")


@pytest.mark.parametrize("status", [401, 403])
def test_http_auth_error_is_a_credentials_rejection_without_retry(igm, status):
    import httpx

    seen, state = igm
    state["response"] = httpx.Response(status, text="denied")
    with pytest.raises(ov.VertoError) as info:
        ov.convert([(1, 2)], 4265, 6706, use_cache=False)
    assert info.value.credentials_rejected
    assert len(seen) == 1


def test_skip_invalid_does_not_bisect_on_rejected_credentials(igm):
    import httpx

    seen, state = igm
    state["response"] = httpx.Response(200, json={"stato": "errore", "dove": "chiave", "messaggio": "Non valida"})
    with pytest.raises(ov.VertoError):
        ov.convert_skipping([(1, 2), (3, 4), (5, 6), (7, 8)], 4265, 6706)
    assert len(seen) == 1


def test_outside_grid_error_is_not_a_credentials_rejection():
    exc = ov.VertoError("coordinate fuori griglia", "Proj")
    assert exc.outside_grid
    assert not exc.credentials_rejected


# --- retired EPSG codes -----------------------------------------------------


def test_reftable_lists_replacements_not_retired_codes():
    from openverto.refdata import RETIRED_EPSG

    assert not set(RETIRED_EPSG) & set(REF_TABLE)
    assert set(RETIRED_EPSG.values()) <= set(REF_TABLE)


@pytest.mark.parametrize("old,new", [(6707, 7791), (6708, 7792), (6709, 7793), (6876, 7795)])
@pytest.mark.parametrize("command", ["convert", "roundtrip", "targets", "inspect", "batch", "geojson"])
def test_cli_retired_code_names_its_replacement(igm, tmp_path, command, old, new):
    from typer.testing import CliRunner

    from openverto.cli import app

    seen, _ = igm
    f = tmp_path / "in.csv"
    f.write_text("e,n\n1,2\n")
    gj = tmp_path / "in.geojson"
    gj.write_text('{"type":"Point","coordinates":[1,2]}')
    args = {
        "convert": ["convert", "--from", "3003", "--to", str(old), "--no-cache", "1", "2"],
        "roundtrip": ["roundtrip", "--from", "3003", "--to", str(old), "1", "2"],
        "targets": ["targets", str(old)],
        "inspect": ["inspect", str(old)],
        "batch": ["batch", str(f), "--from", "3003", "--to", str(old), "--e-col", "e", "--n-col", "n"],
        "geojson": ["geojson", str(gj), "--from", "3003", "--to", str(old)],
    }[command]
    res = CliRunner().invoke(app, args)
    assert res.exit_code == 3, res.output
    assert str(new) in res.output
    assert not seen


def test_cli_batch_accepts_new_code(igm, tmp_path):
    from typer.testing import CliRunner

    from openverto.cli import app

    seen, _ = igm
    f = tmp_path / "in.csv"
    f.write_text("e,n\n1,2\n")
    res = CliRunner().invoke(app, ["batch", str(f), "--from", "23033", "--to", "7791", "--e-col", "e", "--n-col", "n"])
    assert res.exit_code == 0, res.output
    assert seen[-1]["outEpsg"] == 7791


def test_library_retired_code_ignores_old_cached_results(igm, tmp_path):
    seen, _ = igm
    (tmp_path / "conversions.json").write_text('{"3003:6707:1.0:2.0": [9.0, 9.0]}')
    with pytest.raises(ov.VertoError, match="7791"):
        ov.convert([(1, 2)], 3003, 6707)
    with pytest.raises(ov.VertoError, match="7791"):
        ov.convert_skipping([(1, 2)], 3003, 6707)
    assert not seen


def test_skip_invalid_does_not_bisect_on_unsupported_epsg(igm):
    import httpx

    seen, state = igm
    state["response"] = httpx.Response(200, json={"stato": "errore", "dove": "outEpsg", "messaggio": "sistema di riferimento non supportato"})
    with pytest.raises(ov.VertoError):
        ov.convert_skipping([(1, 2), (3, 4), (5, 6), (7, 8)], 4265, 6706)
    assert len(seen) == 1


def test_systems_refreshes_a_list_cached_before_the_service_change(igm, tmp_path, monkeypatch):
    sysmod = sys.modules["openverto.systems"]

    (tmp_path / "systems.json").write_text('[{"epsg": 6707, "descrizione": "RDN2008 / TM32"}]')
    fresh = [{"epsg": 7791, "descrizione": "RDN2008 / UTM zone 32N (E-N)"}]
    monkeypatch.setattr(sysmod, "info", lambda: {"srsSupportati": fresh})
    assert sysmod.systems() == fresh
    assert sysmod.systems() == fresh


def test_systems_keeps_the_old_list_when_offline(igm, tmp_path, monkeypatch):
    sysmod = sys.modules["openverto.systems"]

    old = [{"epsg": 6707, "descrizione": "RDN2008 / TM32"}]
    (tmp_path / "systems.json").write_text('[{"epsg": 6707, "descrizione": "RDN2008 / TM32"}]')

    def down():
        raise OSError("offline")

    monkeypatch.setattr(sysmod, "info", down)
    assert sysmod.systems() == old
