# LOG

## 2026-06-09 — v0.2.2 — validazione upfront target in `batch`

- `batch`: check immediato che `--to` sia un target valido per `--from`; fallisce prima di leggere il CSV con messaggio chiaro (`Run 'openverto targets <from>'`).
- 2 nuovi test offline (`test_batch_rejects_invalid_target`, `test_batch_accepts_valid_target_combination`).

## 2026-06-09 — docs: disclaimer non-affiliazione + nota Z/M planimetrica

- Spunti da `sag1687/geobridge` (plugin QGIS per lo stesso servizio IGM): aggiunti due punti che mancavano.
- README: nuova sezione **Disclaimer** (strumento indipendente/non ufficiale, non affiliato IGM; servizio/dati/risultati restano proprietà IGM; link alle condizioni d'uso ufficiali).
- README: nota in "Note tecniche" — la conversione IGM è **planimetrica**, le quote Z/M non vengono trasformate; openverto le preserva inalterate nei GeoJSON.

## 2026-06-09 — docs: spec OpenAPI dell'API IGM (reverse engineering)

- Aggiunta `docs/openapi.yaml`: documentazione OpenAPI 3.1.0 **non ufficiale** dell'endpoint IGM Verto Online, ricostruita dal manuale (`ref/`) e dal codice. Modella fedelmente il servizio RPC: **un solo path POST** discriminato da `richiesta` (`info`/`conversione`), **errori in HTTP 200** con `stato: errore`, `utente`/`chiave` obbligatori ma ignorati, ordine assi e-prima, limite 32000, no conversioni stesso datum. Esempi nominati dal manuale (typo `"x"`→`"n"` corretto). `security: []` (servizio senza auth).
- Validata con `openapi-spec-validator` (OK) e `redocly lint` (solo warning 4xx, lasciato di proposito: il servizio non usa 4xx).
- README: nuova sezione "API del servizio IGM" che linka la spec.

## 2026-06-09 — docs: riferimento CLI completo

- Aggiunta `docs/cli.md`: guida completa a tutti i comandi e opzioni (opzioni globali, codici di uscita, comportamento `--skip-invalid`, gotcha ordine assi, output strutturato in `batch`).
- README: aggiunto link al riferimento CLI sopra la tabella dei comandi.

## 2026-06-08 — v0.2.1 — throttle tra i blocchi

- Aggiunto un **throttle** (default **2s**) tra i blocchi di conversione: scatta **solo** quando un job supera le 32000 coordinate (più richieste); una conversione singola non viene mai rallentata. Configurabile via `--throttle` (CLI) e `set_throttle()` (libreria), `0` per disabilitare.
- Nota "non abusare" del servizio IGM gratuito nell'help della CLI e nel README.
- Implementato in `convert` (pausa tra chunk) e `convert_skipping` (pausa tra richieste, solo job > MAX_COORD). +1 test (throttle solo multi-batch); fixture `_no_throttle` per non rallentare gli altri test. 23 test, ruff ok.

## 2026-06-08 — v0.2.0 — batch legge il CSV con DuckDB

- `batch` ora legge il CSV di input via **DuckDB** (dipendenza core aggiunta): autodetect del delimitatore (`,`, `;`, tab, `|`) rilevato dalla **riga di header**, nuova opzione `--decimal` (`.` default, `,` per CSV italiani tipo `12,4924`), supporto **stdin** (`-`) e stdout (default senza `--out`).
- Niente formati spaziali: l'idea iniziale (export GPKG/FGB/GeoParquet/SHP via estensione spatial) è stata abbandonata dopo una sonda empirica — driver `Parquet` assente, FGB riordina le feature, GeoParquet nativo tagga CRS84 invece dell'EPSG. Si usa DuckDB solo per I/O CSV robusto.
- Bug risolto: con `decimal_separator=','` lo sniffer di DuckDB sceglie la virgola come delimitatore su righe tutte-numeriche → rilevo io il delimitatore dall'header escludendo la virgola, poi `read_csv` con `delim` esplicito.
- Regressione risolta (lettura tipizzata riformattava le colonne attributo, es. `19.90`→`19.9`, `1000,50`→`1000.5`): ora `read_csv` con `all_varchar=true` tiene ogni cella come stringa grezza; la virgola→punto è normalizzata **solo** sulle colonne x/y dentro `batch`.
- Allineamento libreria↔CLI: esportati `read_csv_file`, `resolve_column`, `rows_to_geojson` in `openverto/__init__.py` così il workflow di `batch` è riproducibile da `import openverto`.
- README: badge (PyPI/GitHub/DeepWiki/MIT/Newsletter) stile opensdmx + link al servizio IGM Verto Online + sezione formato CSV di default.
- Test: +6 offline (delimitatore `;`, celle grezze preservate, header numerico-regression, stdin, colonna mancante, alias). 22 passati, ruff pulito, wheel ok.
- Skill `verto-explorer` aggiornata (v1.1) con la lettura DuckDB; nuova guida d'installazione skill `docs/skill/README.md` (stile opensdmx, `npx skills add ondata/openverto`), linkata dal README.
- Manuale ufficiale IGM scaricato in `ref/` (PDF + markdown via `lit`).
- Gestito con OpenSpec: change `batch-duckdb-csv` (ex `duckdb-spatial-export`, ridimensionata).
- TODO: bump versione + eventuale release (dipendenza core nuova).

## 2026-06-08 — v0.1.1

- Subrelease patch: aggiunta sezione `Examples:` nel docstring di **ogni** sottocomando CLI (`systems`, `convert`, `inspect`, `detect`, `targets`, `roundtrip`, `batch`, `geojson`, `cache`, `doctor`) — almeno un esempio utile per LLM, sul modello di `opensdmx`.
- `convert`: nota esplicita che le opzioni globali (`-o/--output`) vanno **prima** del sottocomando (`openverto -o jsonl convert ...`), non dopo — causa frequente di `No such option: -o`.

## 2026-06-08

- Porting Python del CLI Go `printing-press/library/verto` → **openverto** (libreria + CLI, stile `opensdmx`).
- Architettura `src/openverto/`: `base` (HTTP + `VertoError`), `refdata` (tabella statica 20 EPSG), `systems` (endpoint `info` + cache), `transform` (convert/chunking/bisezione, inspect/targets/roundtrip), `detect` (euristica offline), `cache` (write-through), `geo` (GeoJSON + CSV batch), `cli` (typer).
- Output globale `-o/--output table|json|jsonl|csv` (jsonl ideale per coordinate).
- Verificato sul servizio live IGM: valore golden `4265→6706 (12.4924,41.8902)` esatto; **coordinate a mare** vicino all'Italia (Tirreno) valide; **fuori Italia** (Parigi/oceano) → `errore/Proj/outside grid`.
- Gestione errori fuori-griglia con hint in italiano + suggerimento `--skip-invalid` in batch per isolare i punti fuori Italia.
- Fix collisione di nome modulo `convert` ↔ funzione `convert`: rinominato modulo in `transform.py`.
- Test: 20 offline (refdata/detect/chunking/bisezione/cache/geojson-int) + 4 live skippable (`-m live`). Ruff pulito. Build wheel ok.
- Agent Skill `verto-explorer` (workflow 4 fasi per LLM), scritta facendo dogfooding reale dei comandi.
- Revisione GIS di help+skill: convenzione assi est-first + caveat ordine lat/long del registro EPSG; help `--from/--to` completati; fix perdita markup Rich su testo tra parentesi quadre.
- Confronto con `gdaltransform` (PROJ senza griglie): nessun erroraccio, scarto datum 0.1–2.8 m come atteso (IGM95→RDN2008 a 0.11 m conferma datum/assi corretti). Vedi `docs/evaluation.md` + test di regressione skippable.
- CI (`.github/workflows/ci.yml`), `docs/release.md` (tag + twine), `.gitignore`, `LICENSE` MIT.
- Repo pubblico creato: https://github.com/ondata/openverto (branch `main`, CI attiva).
- ~~TODO: primo tag + pubblicazione PyPI~~ → fatto con **v0.1.1**: https://pypi.org/project/openverto/0.1.1/ (la 0.1.0 non è mai stata pubblicata).
