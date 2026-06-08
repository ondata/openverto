# openverto

[![PyPI version](https://img.shields.io/pypi/v/openverto)](https://pypi.org/project/openverto/)
[![GitHub](https://img.shields.io/badge/github-ondata%2Fopenverto-blue?logo=github)](https://github.com/ondata/openverto)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/ondata/openverto)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Newsletter](https://img.shields.io/badge/newsletter-ondata-FF6719?logo=substack)](https://ondata.substack.com/)

> Tool sperimentale — aiutaci a testarlo [aprendo issue](https://github.com/ondata/openverto/issues) o inviando feedback.

CLI e libreria Python per il servizio ufficiale **[IGM Verto Online](https://igmi.esercito.difesa.it/servizi/verto-online/)**: trasforma coordinate tra tutti i sistemi di riferimento italiani (Roma40, ED50, IGM95, ETRS89, RDN2008) **senza installare le griglie NTv2**, appoggiandosi al servizio autorevole dell'Istituto Geografico Militare.

Pensato per essere **orchestrato da agenti AI**: output `--json`/`--jsonl`/`--csv`, non interattivo, pipeable, read-only. L'intelligenza sugli EPSG (`inspect`, `detect`, `targets`) è completamente **offline**.

> **Con un'AI.** openverto funziona benissimo da solo, ma **può essere guidato da un agente AI**. Per un'esperienza interattiva — identificazione del sistema di origine, scelta di un target valido, conversione e verifica della copertura — abbinalo alla Agent Skill [`verto-explorer`](skills/verto-explorer/SKILL.md) inclusa nel repo. Vedi la [**guida d'installazione**](docs/skill/README.md) per i passi.

## Installazione

Come strumento CLI (consigliato):

```bash
uv tool install openverto
```

Come libreria:

```bash
uv add openverto    # oppure: pip install openverto
```

## Avvio rapido (CLI)

```bash
# i 20 sistemi di riferimento supportati (cache offline dopo la prima volta)
openverto systems

# converti una coordinata Roma40 -> RDN2008 (lon lat)
openverto convert --from 4265 --to 6706 12.4924 41.8902

# asse, fuso e false easting prima di una conversione proiettata
openverto inspect 3003

# converti un CSV di punti Gauss-Boaga (colonne est/nord) in RDN2008/TM32
openverto batch catasto.csv --from 3003 --to 6707 --e-col est --n-col nord --out out.csv

# CSV all'italiana (delimitatore ; e virgola decimale), da stdin verso stdout
cat comuni.csv | openverto batch - --from 4265 --to 6706 --decimal , --e-col lon --n-col lat

# riproietta le geometrie di un GeoJSON
openverto geojson aree.geojson --from 4230 --to 6706 --out out.geojson
```

### Lettura del CSV (comando `batch`)

Il CSV di input è letto con **DuckDB**: il **delimitatore** (`,`, `;`, tab, `|`) è
rilevato automaticamente, non va dichiarato.

- **Formato di default, nessuna opzione richiesta**: CSV con prima riga di
  intestazione, separatore decimale **punto** (`12.4924`). Il delimitatore può
  essere virgola o punto e virgola: viene riconosciuto da solo.
- **CSV all'italiana**: per coordinate con la **virgola decimale** (`12,4924`)
  aggiungi `--decimal ,`.
- **stdin/stdout**: usa `-` come file per leggere da stdin; ometti `--out` per
  scrivere su stdout.

## Formati di output

Globale, con `-o/--output`:

```bash
openverto systems                 # tabella (default in terminale)
openverto -o json systems         # JSON
openverto -o jsonl convert ...    # JSON Lines: un oggetto compatto per riga (ideale per coordinate)
openverto -o csv convert ...      # CSV
```

`jsonl` è il formato più adatto allo streaming di coordinate verso `jq` o pipeline.

## Comandi

| Comando | Descrizione |
|---|---|
| `systems` | Elenco dei sistemi di riferimento supportati (EPSG + descrizione) |
| `convert` | Converte una o più coordinate (`e n`, o `e,n` da stdin) |
| `batch` | Converte un CSV (letto con DuckDB: delimitatore auto, `--decimal`, `-`=stdin) in CSV o GeoJSON (auto-chunk a 32000, `--skip-invalid`) |
| `geojson` | Riproietta le geometrie di un file GeoJSON |
| `inspect` | Famiglia datum, ordine assi, unità, fuso, false easting di un EPSG |
| `detect` | Indovina il sistema di origine di una coordinata dalla sua magnitudine |
| `targets` | Destinazioni di conversione valide per un EPSG (datum diverso) |
| `roundtrip` | Converte A→B→A e riporta l'errore residuo del datum |
| `cache` | Ispeziona o svuota la cache offline |
| `doctor` | Verifica la connettività al servizio |

### Funzioni distintive

- **`roundtrip`** — certifica che una catena di datum sia lossless entro tolleranza prima di pubblicare dati.
- **`detect`** — recupera l'EPSG reale di un dataset etichettato vagamente ("UTM", "Gauss-Boaga").
- **`inspect` / `targets`** — disambigua sistemi simili (3003 vs 3004) ed evita destinazioni con lo stesso datum (rifiutate dal servizio).
- **cache offline** — replay riproducibile delle conversioni in CI o pipeline offline.

## Uso come libreria

```python
import openverto as ov

# elenco sistemi
ov.systems()                          # [{"epsg": 4265, "descrizione": "Monte Mario"}, ...]

# conversione (e=est/lon, n=nord/lat); auto-chunk + cache
ov.convert([(12.4924, 41.8902)], 4265, 6706)
# -> [(12.4921961827, 41.8908506304)]

# intelligenza offline (nessuna chiamata di rete)
ov.inspect(3003)
ov.targets(3003)
ov.detect(2300000, 4640000)           # {"kind": "projected", "candidate_epsg": [3004], ...}

# lettura CSV robusta come la CLI (delimitatore auto; '-' = stdin)
# le celle restano stringhe grezze: normalizza la virgola solo sulle colonne x/y
header, records = ov.read_csv_file("comuni.csv", decimal=",")
e_idx = ov.resolve_column(header, "lon", ov.geo.E_ALIASES)

# salta le coordinate fuori griglia isolandole per bisezione
results, skipped = ov.convert_skipping(coords, 3003, 6707)

# errore residuo di una catena di datum
ov.roundtrip([(1500000, 4640000)], 3003, 6707)
```

## Autenticazione

Nessuna. Il servizio è libero e gratuito; i campi `utente`/`chiave` richiesti dall'API sono segnaposto, riempiti automaticamente.

## Note tecniche

- Le coordinate geografiche sono **sempre in gradi sessadecimali**.
- Le conversioni **tra sistemi con lo stesso datum** non sono ammesse dal servizio (vedi `targets`).
- Il servizio accetta al massimo **32000 coordinate** per richiesta; `batch` esegue automaticamente il chunking.
- La griglia IGM copre l'Italia e i mari circostanti: coordinate fuori copertura vengono rifiutate (usa `detect`/`inspect` per controllare assi e EPSG).
- **Il servizio IGM è gratuito e pubblico: non abusarne.** Quando un job supera le **32000 coordinate** (il limite per richiesta) e viene quindi spezzato in più blocchi, openverto mette una pausa di **2 secondi tra un blocco e l'altro** (`--throttle`, o `set_throttle()` nella libreria). Una conversione singola (≤32000) non viene mai rallentata. `--throttle 0` disabilita la pausa, ma usalo con criterio.

## Crediti

Servizio dati: [IGM Verto Online](https://igmi.esercito.difesa.it/servizi/verto-online/), Istituto Geografico Militare.

## Licenza

MIT.
