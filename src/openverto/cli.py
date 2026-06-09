"""CLI for openverto — IGM Verto Online coordinate transforms."""

from __future__ import annotations

import csv
import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from . import cache as cache_mod
from .base import VertoError, set_extra_headers, set_throttle, set_timeout
from .transform import (
    MAX_COORD,
    convert as lib_convert,
    convert_skipping as lib_convert_skipping,
    inspect as lib_inspect,
    roundtrip as lib_roundtrip,
    targets as lib_targets,
)
from .detect import detect as lib_detect
from .geo import (
    E_ALIASES,
    N_ALIASES,
    read_csv_file,
    reproject_geojson,
    resolve_column,
    rows_to_geojson,
)
from .systems import systems as lib_systems

# Exit codes (agent-friendly, mirror the Go CLI).
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_API = 5

console = Console()
err = Console(stderr=True)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "openverto — official IGM coordinate transforms between Italian reference "
        "systems (Roma40, ED50, IGM95, ETRS89, RDN2008).\n\n"
        "Axis order: coordinates are always 'e' (est = easting OR longitude) first, "
        "'n' (nord = northing OR latitude) second. Geographic values are decimal "
        "degrees. NOTE: this east-first order is the service's convention and is the "
        "reverse of the EPSG-registry lat/long axis order of geographic CRS like "
        "4265/4230/4670/6706 — pass longitude first. GeoJSON positions (x, y) "
        "already equal (e, n), so reprojecting GeoJSON needs no swap.\n\n"
        "Conversions between two systems of the SAME datum are rejected by the "
        "service; use 'targets' to list valid destinations.\n\n"
        "Global output: -o/--output table|json|jsonl|csv (jsonl is one compact "
        "object per line, ideal for coordinates).\n\n"
        "The IGM Verto Online service is free and public: please don't abuse it. "
        "Jobs over 32000 coordinates are split into batches, spaced by --throttle "
        "seconds (default 2); a single batch is never delayed. Set 0 to disable."
    ),
)

_output = "table"


# --------------------------------------------------------------------------- #
# output helpers
# --------------------------------------------------------------------------- #
def _fmt(v) -> str:
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    return str(v)


def _emit(data, *, title: str | None = None) -> None:
    """Render ``data`` (a list of dicts, or a single dict) per the output mode."""
    if _output == "json":
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return
    if _output == "jsonl":
        items = data if isinstance(data, list) else [data]
        for item in items:
            sys.stdout.write(json.dumps(item, ensure_ascii=False) + "\n")
        return
    if _output == "csv":
        rows = data if isinstance(data, list) else [data]
        if not rows:
            return
        keys = list(rows[0].keys())
        w = csv.writer(sys.stdout)
        w.writerow(keys)
        for r in rows:
            w.writerow([_fmt(r.get(k, "")) for k in keys])
        return
    _emit_table(data, title=title)


def _emit_table(data, *, title: str | None = None) -> None:
    if isinstance(data, dict):
        t = Table(show_header=False, box=None, title=title)
        t.add_column("field", style="cyan", no_wrap=True)
        t.add_column("value")
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            t.add_row(k, _fmt(v))
        console.print(t)
        return
    if not data:
        err.print("[dim]no results[/dim]")
        return
    keys = list(data[0].keys())
    t = Table(title=title)
    for k in keys:
        t.add_column(k, overflow="fold")
    for r in data:
        t.add_row(*[_fmt(r.get(k, "")) for k in keys])
    console.print(t)


def _die(msg: str, code: int) -> None:
    err.print(f"[red]error:[/red] {msg}")
    raise typer.Exit(code)


def _parse_epsg(s: str) -> int:
    s = s.strip().upper().removeprefix("EPSG:").strip()
    try:
        return int(s)
    except ValueError:
        _die(f"invalid EPSG code {s!r}: want an integer like 3003", EXIT_USAGE)


def _read_coord_args(args: list[str]) -> list[tuple[float, float]]:
    """Parse coordinate pairs from positional args, or 'e,n' lines from stdin."""
    if args:
        if len(args) % 2 != 0:
            _die(f"coordinates must come in pairs of <e> <n>; got {len(args)} values", EXIT_USAGE)
        coords = []
        for i in range(0, len(args), 2):
            try:
                coords.append((float(args[i]), float(args[i + 1])))
            except ValueError:
                _die(f"invalid coordinate value in {args[i]!r} {args[i+1]!r}", EXIT_USAGE)
        return coords
    coords = []
    if sys.stdin.isatty():
        return coords
    for lineno, raw in enumerate(sys.stdin, 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        fields = [f for f in _split_coord(raw) if f != ""]
        if len(fields) != 2:
            _die(f"stdin line {lineno}: want two values 'e,n', got {raw!r}", EXIT_USAGE)
        try:
            coords.append((float(fields[0]), float(fields[1])))
        except ValueError:
            _die(f"stdin line {lineno}: invalid number in {raw!r}", EXIT_USAGE)
    return coords


def _split_coord(raw: str) -> list[str]:
    for sep in (",", ";", "\t"):
        raw = raw.replace(sep, " ")
    return raw.split(" ")


def _handle_verto_error(exc: VertoError, *, batch: bool = False) -> None:
    if exc.outside_grid:
        hint = (
            f"{exc}\n"
            "→ la coordinata cade fuori dalla copertura della griglia IGM "
            "(Italia e mari circostanti). I punti a mare vicini all'Italia sono "
            "validi; quelli in altri Paesi o in mare aperto no.\n"
            "  • controlla EPSG di origine e ordine degli assi: "
            "'openverto detect <e> <n>' e 'openverto inspect <epsg>'"
        )
        if batch:
            hint += (
                "\n  • una sola coordinata fuori griglia fa fallire l'intera "
                "richiesta: usa --skip-invalid per isolare e saltare i punti fuori Italia"
            )
        _die(hint, EXIT_USAGE)
    _die(str(exc), EXIT_USAGE)


# --------------------------------------------------------------------------- #
# global callback
# --------------------------------------------------------------------------- #
def _version_cb(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def _main(
    output: str = typer.Option("table", "--output", "-o", help="table | json | jsonl | csv"),
    timeout: float = typer.Option(30.0, "--timeout", help="Per-request timeout in seconds"),
    throttle: float = typer.Option(2.0, "--throttle", help="Seconds between batches for jobs over 32000 coords (be kind to the free IGM service; 0 to disable)"),
    header: Optional[list[str]] = typer.Option(None, "--header", "-H", help="Extra HTTP header 'Name: Value' (repeatable)"),
    version: bool = typer.Option(False, "--version", "-V", callback=_version_cb, is_eager=True, help="Show version and exit"),
) -> None:
    global _output
    if output not in ("table", "json", "jsonl", "csv"):
        _die(f"invalid --output {output!r}; choose table, json, jsonl, csv", EXIT_USAGE)
    _output = output
    set_timeout(timeout)
    set_throttle(throttle)
    if header:
        parsed = {}
        for h in header:
            if ":" not in h:
                _die(f"invalid header {h!r}: use 'Name: Value'", EXIT_USAGE)
            name, _, val = h.partition(":")
            parsed[name.strip()] = val.strip()
        set_extra_headers(parsed)


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
@app.command()
def systems(refresh: bool = typer.Option(False, "--refresh", help="Force a live fetch (ignore cache)")):
    """List the Italian reference systems supported by Verto Online.

    Examples:

      openverto systems
      openverto -o jsonl systems
    """
    try:
        rows = lib_systems(refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        _die(f"could not fetch systems: {exc}", EXIT_API)
    _emit(rows, title="IGM Verto — supported reference systems")


@app.command()
def convert(
    coords: Optional[list[str]] = typer.Argument(None, help="Coordinate pairs: e n [e n ...]. Omit to read 'e,n' lines from stdin."),
    from_epsg: str = typer.Option(..., "--from", help="Source EPSG (e.g. 3003)"),
    to_epsg: str = typer.Option(..., "--to", help="Target EPSG (e.g. 6706)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the offline conversion cache"),
):
    """Convert one or more coordinates between reference systems (e=est/lon, n=nord/lat).

    Axis order is always e (est/lon) first, n (nord/lat) second.

    Examples:

      openverto convert --from 23033 --to 6706 290000 4640000
      openverto -o jsonl convert --from 4265 --to 6706 12.4924 41.8902
      printf '290000,4640000\\n' | openverto -o csv convert --from 23033 --to 6706

    Note: global options like -o/--output go BEFORE the subcommand
    (openverto -o jsonl convert ...), never after it.
    """
    in_e = _parse_epsg(from_epsg)
    out_e = _parse_epsg(to_epsg)
    pairs = _read_coord_args(coords or [])
    if not pairs:
        _die("no coordinates given (pass 'e n' pairs or pipe 'e,n' lines on stdin)", EXIT_USAGE)
    try:
        out = lib_convert(pairs, in_e, out_e, use_cache=not no_cache)
    except VertoError as exc:
        _handle_verto_error(exc, batch=len(pairs) > 1)
    except Exception as exc:  # noqa: BLE001
        _die(str(exc), EXIT_API)
    rows = [
        {"in_e": pairs[i][0], "in_n": pairs[i][1], "out_e": out[i][0], "out_n": out[i][1]}
        for i in range(len(pairs))
    ]
    _emit(rows)


@app.command()
def inspect(epsg: list[str] = typer.Argument(..., help="One or more EPSG codes")):
    """Show datum family, axis order, units, zone and false easting for an EPSG.

    Examples:

      openverto inspect 3003
      openverto -o json inspect 3003 6706
    """
    cards = []
    for a in epsg:
        code = _parse_epsg(a)
        try:
            cards.append(lib_inspect(code))
        except KeyError:
            _die(f"EPSG {code} is not IGM-supported; run 'openverto systems'", EXIT_NOT_FOUND)
    _emit(cards if len(cards) > 1 else cards[0])


@app.command()
def detect(e: float = typer.Argument(...), n: float = typer.Argument(...)):
    """Guess the likely source reference system of a coordinate from its magnitude.

    Examples:

      openverto detect 290000 4640000
      openverto -o json detect 1500000 4640000
    """
    _emit(lib_detect(e, n))


@app.command()
def targets(epsg: str = typer.Argument(..., help="Source EPSG")):
    """List the reference systems you can convert a given EPSG into.

    Examples:

      openverto targets 3003
      openverto -o csv targets 3003
    """
    code = _parse_epsg(epsg)
    try:
        rows = lib_targets(code)
    except KeyError:
        _die(f"EPSG {code} is not IGM-supported; run 'openverto systems'", EXIT_NOT_FOUND)
    _emit(rows, title=f"valid conversion targets for EPSG {code}")


@app.command()
def roundtrip(
    coords: Optional[list[str]] = typer.Argument(None, help="Coordinate pairs: e n [e n ...]"),
    from_epsg: str = typer.Option(..., "--from", help="Source EPSG (e.g. 3003)"),
    to_epsg: str = typer.Option(..., "--to", help="Round-trip-through EPSG, different datum (e.g. 6707)"),
):
    """Convert A->B->A and report the residual error of the transform.

    The residual is the gap between the original coordinate and itself after the
    forward + inverse transform (datum shift + projection). residual_e/residual_n
    are exact in the source unit; residual_m is an approximate distance in metres
    (for geographic sources, a latitude-aware spherical approximation).

    Examples:

      openverto roundtrip --from 23033 --to 6706 290000 4640000
      openverto -o json roundtrip --from 3003 --to 6707 1500000 4640000
    """
    in_e = _parse_epsg(from_epsg)
    out_e = _parse_epsg(to_epsg)
    pairs = _read_coord_args(coords or [])
    if not pairs:
        _die("no coordinates given", EXIT_USAGE)
    try:
        report = lib_roundtrip(pairs, in_e, out_e)
    except VertoError as exc:
        _handle_verto_error(exc)
    except Exception as exc:  # noqa: BLE001
        _die(str(exc), EXIT_API)
    if _output == "table":
        _emit(report["points"], title=f"roundtrip {in_e} -> {out_e} -> {in_e}")
        err.print(
            f"max residual: {report['max_residual_m']:.4g} m   "
            f"mean: {report['mean_residual_m']:.4g} m   ({report['source_unit']} source)"
        )
    else:
        _emit(report)


@app.command()
def batch(
    file: str = typer.Argument(..., help="Input CSV file ('-' for stdin)"),
    from_epsg: str = typer.Option(..., "--from", help="Source EPSG (e.g. 3003)"),
    to_epsg: str = typer.Option(..., "--to", help="Target EPSG, different datum (e.g. 6707)"),
    e_col: str = typer.Option("", "--e-col", help="East/longitude column (auto-detected if empty)"),
    n_col: str = typer.Option("", "--n-col", help="North/latitude column (auto-detected if empty)"),
    decimal: str = typer.Option(".", "--decimal", help="Decimal separator of the input CSV: '.' or ',' (Italian-style 12,4924)"),
    out: str = typer.Option("", "--out", help="Output file (default stdout)"),
    fmt: str = typer.Option("csv", "--format", help="csv | geojson"),
    skip_invalid: bool = typer.Option(False, "--skip-invalid", help="Bisect and skip coordinates the service rejects"),
    rejects: str = typer.Option("", "--rejects", help="Write skipped rows to this CSV"),
):
    """Convert a whole CSV of coordinates to CSV or GeoJSON (auto-chunks at 32000).

    The CSV is read with DuckDB. Default input format, no option needed: a header
    row and a dot decimal separator (12.4924); the delimiter (',', ';', tab, '|')
    is auto-detected. Use --decimal ',' for Italian-style CSVs whose coordinates
    look like 12,4924. Pass '-' as the file to read from stdin; omit --out to
    write to stdout.

    Examples:

      openverto batch catasto.csv --from 3003 --to 6707 --e-col est --n-col nord --out out.csv
      openverto batch points.csv --from 3003 --to 6706 --format geojson --out out.geojson
      openverto batch comuni.csv --from 4265 --to 6706 --decimal , --e-col lon --n-col lat
      cat comuni.csv | openverto batch - --from 4265 --to 6706 --decimal ,
      openverto batch mixed.csv --from 4265 --to 6706 --skip-invalid --rejects bad.csv
    """
    in_e = _parse_epsg(from_epsg)
    out_e = _parse_epsg(to_epsg)
    try:
        valid_targets = lib_targets(in_e)
    except KeyError:
        _die(f"EPSG {in_e} is not IGM-supported; run 'openverto systems'", EXIT_NOT_FOUND)
    if out_e not in {r["epsg"] for r in valid_targets}:
        _die(
            f"EPSG {out_e} is not a valid target for EPSG {in_e}. "
            f"Run 'openverto targets {in_e}' to see valid options.",
            EXIT_USAGE,
        )
    if fmt not in ("csv", "geojson"):
        _die(f"--format must be 'csv' or 'geojson', got {fmt!r}", EXIT_USAGE)
    try:
        header, records = read_csv_file(file, decimal=decimal)
        e_idx = resolve_column(header, e_col, E_ALIASES)
        n_idx = resolve_column(header, n_col, N_ALIASES)
    except (OSError, ValueError) as exc:
        _die(str(exc), EXIT_USAGE)

    pairs = []
    for i, rec in enumerate(records):
        if e_idx >= len(rec) or n_idx >= len(rec):
            _die(f"row {i+1}: too few fields for the e/n columns", EXIT_USAGE)
        e_raw, n_raw = rec[e_idx].strip(), rec[n_idx].strip()
        if decimal == ",":
            e_raw, n_raw = e_raw.replace(",", "."), n_raw.replace(",", ".")
        try:
            pairs.append((float(e_raw), float(n_raw)))
        except ValueError:
            _die(f"row {i+1}: invalid e/n value", EXIT_USAGE)

    skipped: set[int] = set()
    try:
        if skip_invalid:
            results, skip_list = lib_convert_skipping(pairs, in_e, out_e)
            skipped = set(skip_list)
        else:
            results = lib_convert(pairs, in_e, out_e)
    except VertoError as exc:
        _handle_verto_error(exc, batch=True)
    except Exception as exc:  # noqa: BLE001
        _die(str(exc), EXIT_API)

    # Structured output modes go to stdout and ignore --out/--format.
    if _output in ("json", "jsonl", "csv"):
        rows = []
        for i, rec in enumerate(records):
            if i in skipped:
                continue
            row = {header[j]: rec[j] for j in range(len(header)) if j < len(rec)}
            row["e_out"], row["n_out"] = results[i][0], results[i][1]
            rows.append(row)
        _emit(rows)
    else:
        sink = open(out, "w", newline="", encoding="utf-8") if out else sys.stdout
        try:
            if fmt == "geojson":
                json.dump(rows_to_geojson(header, records, results, skipped, out_e), sink, ensure_ascii=False, indent=2)
                sink.write("\n")
            else:
                w = csv.writer(sink)
                w.writerow(list(header) + ["e_out", "n_out"])
                for i, rec in enumerate(records):
                    if i in skipped:
                        continue
                    w.writerow(list(rec) + [_fmt(results[i][0]), _fmt(results[i][1])])
        finally:
            if sink is not sys.stdout:
                sink.close()
        if out:
            err.print(f"wrote {len(records) - len(skipped)} row(s) to {out}")

    if skipped:
        rowlist = ", ".join(str(i + 1) for i in sorted(skipped)[:10])
        err.print(f"[yellow]skipped {len(skipped)} coordinate(s) outside the IGM grid (rows: {rowlist})[/yellow]")
        if rejects:
            with open(rejects, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(header)
                for i in sorted(skipped):
                    w.writerow(records[i])
            err.print(f"wrote rejected rows to {rejects}")


@app.command()
def geojson(
    file: str = typer.Argument(..., help="Input GeoJSON file ('-' for stdin)"),
    from_epsg: str = typer.Option(..., "--from", help="Source EPSG of the input positions"),
    to_epsg: str = typer.Option(..., "--to", help="Target EPSG, different datum"),
    out: str = typer.Option("", "--out", help="Output file (default stdout)"),
):
    """Reproject every geometry coordinate in a GeoJSON file between systems.

    GeoJSON positions (x, y) equal (e, n) — longitude, latitude for geographic
    systems — matching the service's axis order directly, with no swap needed.

    Examples:

      openverto geojson aree.geojson --from 4230 --to 6706 --out out.geojson
      cat aree.geojson | openverto geojson - --from 4230 --to 6706
    """
    in_e = _parse_epsg(from_epsg)
    out_e = _parse_epsg(to_epsg)
    try:
        raw = sys.stdin.read() if file == "-" else open(file, encoding="utf-8").read()
        doc = json.loads(raw)
    except (OSError, ValueError) as exc:
        _die(f"invalid GeoJSON: {exc}", EXIT_USAGE)
    try:
        doc = reproject_geojson(doc, in_e, out_e)
    except ValueError as exc:
        _die(str(exc), EXIT_USAGE)
    except VertoError as exc:
        _handle_verto_error(exc)
    except Exception as exc:  # noqa: BLE001
        _die(str(exc), EXIT_API)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if out and _output not in ("json", "jsonl"):
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        err.print(f"wrote reprojected GeoJSON to {out}")
    else:
        sys.stdout.write(text + "\n")


@app.command()
def cache(
    stats: bool = typer.Option(False, "--stats", help="Show cache statistics"),
    clear: bool = typer.Option(False, "--clear", help="Delete cached systems and conversions"),
):
    """Inspect or clear the local offline cache of conversions and systems.

    Examples:

      openverto cache --stats
      openverto cache --clear
    """
    if clear:
        removed = cache_mod.clear()
        _emit({"cleared": removed})
        return
    _emit(cache_mod.stats())


@app.command()
def doctor():
    """Verify connectivity to the IGM Verto Online service.

    Examples:

      openverto doctor
      openverto -o json doctor
    """
    info = {"version": __version__, "service": "IGM Verto Online"}
    try:
        sysrows = lib_systems(refresh=True)
        info["status"] = "ok"
        info["systems_available"] = len(sysrows)
        info["max_coord"] = MAX_COORD
    except Exception as exc:  # noqa: BLE001
        info["status"] = "unreachable"
        info["error"] = str(exc)
        _emit(info)
        raise typer.Exit(EXIT_API)
    _emit(info)
