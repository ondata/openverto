---
name: verto-explorer
description: >
  Guided coordinate conversion between Italian reference systems via the
  official IGM Verto Online service, using the openverto CLI. Use this skill
  whenever the user needs to transform, reproject, or identify the CRS of
  coordinates in Italy — even if they don't mention IGM, Verto, or EPSG by name.
  Triggers include: converting points between Gauss-Boaga, UTM-ED50, IGM95,
  RDN2008/ETRF2000 or geographic datums (Roma40, ED50, ETRS89); reprojecting a
  CSV or GeoJSON of Italian coordinates; "what CRS is this file?"; coordinates
  that "land in the sea" or far away (wrong EPSG / swapped axes); certifying a
  datum chain is lossless before publishing open data. Guides the user step by
  step: identify the source system, pick a valid target (different datum),
  convert, and verify coverage and precision.
license: MIT
compatibility: >
  Requires the openverto CLI (openverto systems, convert, batch, geojson,
  inspect, detect, targets, roundtrip, cache, doctor).
metadata:
  author: ondata
  version: "1.0"
---

# Verto Explorer — Guided Coordinate Conversion for Italy

This skill uses the **openverto CLI** to convert coordinates between every
Italian reference system through the authoritative **IGM Verto Online** service,
with no NTv2 grid files installed locally.

Every `openverto` command supports `--help`:

```bash
openverto --help
openverto convert --help
openverto batch --help
```

A global `-o/--output` flag controls structured output: `table` (default),
`json`, **`jsonl`** (one compact object per line — ideal for coordinates), `csv`.
Use it whenever you need to parse results instead of reading a Rich table:

```bash
openverto -o json systems
openverto -o jsonl convert --from 4265 --to 6706 12.4924 41.8902
openverto -o csv batch points.csv --from 3003 --to 6707
```

In structured modes stdout is pure data and errors go to stderr. Exit codes:
`0` ok, `2` usage / out-of-grid input, `3` not found, `5` API error.

## Conventions to apply (read first)

- **Axis order is east-first, always**: `e` = est (easting OR longitude), `n` =
  nord (northing OR latitude). This is the *service* convention and is the
  **reverse of the EPSG-registry lat/long axis order** for geographic CRS like
  `4265`, `4230`, `4670`, `6706`. When a user gives "lat, lon", pass **lon as e,
  lat as n**. GeoJSON positions are `[x, y] = [e, n]`, so they already match —
  no swap when reprojecting GeoJSON.
- **Geographic values are always decimal degrees** (gradi sessadecimali), never
  degrees-minutes-seconds. Convert DMS to decimal first.
- **Same-datum conversions are rejected** (e.g. `6706` → `6707`, both RDN2008).
  Always cross a datum family boundary; check with `targets`.
- **`detect` recovers the projection/zone, never the datum**: magnitude alone
  cannot tell Roma40 from ED50/IGM95/RDN2008. Take the datum from the dataset's
  metadata, not from `detect`.
- **EPSG `4806` (Monte Mario, Rome)** measures longitude from the Monte Mario
  prime meridian (~12.45°E from Greenwich), so a point near Rome has `e ≈ 0`, not
  ~12.5. Do not confuse it with the Greenwich-based `4265`.

Follow the four phases in order. The goal is correct, verified conversions — not
to fire a request blind and risk points landing in the sea.

---

## Phase 1 — Identify the source reference system

Coordinates are useless without their CRS. If the user states the EPSG, confirm
its meaning; if not, recover it.

```bash
# vague label ("UTM", "Gauss-Boaga") or unknown magnitude → guess the system
openverto -o json detect 2300000 4640000
# → kind=projected, candidate_epsg=[3004] (Gauss-Boaga fuso Est), confidence=medium

# confirm datum family, axis order (e=est/lon, n=nord/lat), unit, zone, false easting
openverto -o json inspect 3004
```

Key facts to apply:
- `e` is always **est** (easting OR longitude), `n` is **nord** (northing OR
  latitude). Geographic coordinates are ALWAYS decimal degrees.
- Look-alikes to disambiguate: `3003` vs `3004` (Gauss-Boaga West/East),
  `23032` vs `23033` (ED50 UTM 32/33), `6707`/`6708` (RDN2008 TM32/TM33).
- If `detect` says the point is outside Italy's bounds, the conversion will be
  rejected — re-check the EPSG and whether `e`/`n` are swapped.

## Phase 2 — Pick a valid target

The service **rejects conversions between systems of the same datum** (e.g.
RDN2008 2D geo → RDN2008/TM32). List only valid destinations:

```bash
openverto -o json targets 3003   # excludes the Roma40/Monte Mario family
openverto systems                # full list of the 20 supported systems
```

For Italian open data today, the official target datum is **RDN2008 (ETRF2000)**:
geographic `6706`, or projected `6707`/`6708`/`6709` (TM32/33/34).

## Phase 3 — Convert

```bash
# one or a few coordinates (e first, n second)
openverto -o jsonl convert --from 4265 --to 6706 12.4924 41.8902

# many coordinates piped as 'e,n' lines
printf '12.49,41.89\n13.0,42.0\n' | openverto -o jsonl convert --from 4265 --to 6706

# a whole CSV → CSV (original columns + e_out/n_out) or GeoJSON.
# catasto.csv has columns id,est,nord (Gauss-Boaga Ovest = 3003);
# points.csv has columns e,n (also Gauss-Boaga Ovest = 3003) — auto-detected.
openverto batch catasto.csv --from 3003 --to 6707 --e-col est --n-col nord --out out.csv
openverto batch points.csv  --from 3003 --to 6706 --format geojson --out out.geojson

# reproject the geometries of a GeoJSON file
openverto geojson aree.geojson --from 4230 --to 6706 --out out.geojson
```

`batch` auto-detects common column aliases (est/nord/lon/lat/x/y) and auto-chunks
at the 32000-coordinate service cap. Results are cached for offline replay.

Output field names (verified — parse these directly):
- `convert` rows: `in_e, in_n, out_e, out_n`.
- `batch` in `-o json/jsonl/csv`: the original columns **plus** `e_out, n_out`
  (skipped rows are omitted). In file mode (`--out`, default `table`) it writes
  the original CSV columns plus `e_out, n_out`, or a GeoJSON `FeatureCollection`.
- `detect`: `kind, confidence, candidate_epsg, candidate_names, plausibly_in_italy, reason, note`.

## Phase 4 — Verify coverage and precision

The IGM grid covers **Italy and its surrounding seas only**. A point at sea near
Italy is valid; a point in another country or open ocean is rejected with
`stato: errore, dove: Proj, "Coordinate to transform falls outside grid"`.

- A single out-of-grid coordinate fails the **entire** batch request. Isolate and
  skip the offenders instead of failing the whole file:

  ```bash
  openverto batch mixed.csv --from 4265 --to 6706 --skip-invalid --rejects bad.csv
  ```

  The rejected rows go to `bad.csv`; inspect them — they are usually a wrong EPSG,
  swapped axes, or genuinely-foreign points.

- Before publishing, certify the datum chain is lossless within tolerance:

  ```bash
  openverto -o json roundtrip --from 3003 --to 6707 1500000 4640000
  # reports residual_m per point and max/mean residual in metres (A→B→A)
  ```

- Check connectivity / cache when something looks off:

  ```bash
  openverto doctor
  openverto cache --stats
  openverto cache --clear   # force fresh conversions
  ```

---

## Quick reference — the 20 supported systems by datum family

- **Roma40 / Monte Mario**: `4265` geo, `4806` geo (Rome meridian), `3003`
  Gauss-Boaga Ovest, `3004` Gauss-Boaga Est.
- **ED50**: `4230` geo, `23032`/`23033`/`23034` UTM 32/33/34N.
- **ETRS89 / IGM95**: `4670` geo, `3064`/`3065`/`9716` UTM 32/33/34N,
  `3035` LAEA, `3034` LCC.
- **RDN2008 (ETRF2000)** — current official Italian datum: `6706` geo,
  `6707`/`6708`/`6709` TM32/33/34, `7794` Italy Zone (E-N), `6876` Zone 12.

Conversions are only allowed **across** these families, never within one.
