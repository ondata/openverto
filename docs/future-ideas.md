# Future ideas

## Export spaziale via DuckDB (input CSV/JSON/Parquet generico + output GIS con CRS)

### Idea

Dare in pasto a openverto un file tabellare **generico** (CSV, JSON, Parquet) in cui
l'utente dichiara qual è la colonna X e quale la Y, far convertire le coordinate
da Verto, e produrre in output un **file di punti in formato spaziale vero**
(GeoPackage, FlatGeobuf, Shapefile, GeoParquet) con il **CRS corretto già scritto
nel file**.

Il modulo che fa il lavoro di lettura/scrittura è **DuckDB** (con estensione
`spatial`).

### Punto chiave (la tesi di tutto il design)

**DuckDB fa SOLO I/O. Non riproietta nulla.** La conversione di coordinate resta
esclusivamente di Verto. DuckDB:

1. legge l'input (autodetect di delimitatori/tipi su CSV, parsing JSON anche
   annidato, lettura Parquet);
2. scrive l'output spaziale **etichettando** il CRS di destinazione sulle
   coordinate **già convertite da Verto** — NON trasformandole.

Concretamente l'export è qualcosa come:

```sql
COPY punti TO 'out.gpkg'
  WITH (FORMAT GDAL, DRIVER 'GPKG', SRS 'EPSG:6706');
```

dove `SRS` è solo un'**etichetta**: i valori X/Y nella tabella sono quelli
restituiti da Verto.

**Perché NON usare `ST_Transform` di DuckDB.** L'estensione `spatial` espone
`ST_Transform`/PROJ, e un futuro implementatore sarà tentato di usarlo
scavalcando Verto. Sarebbe un errore che svuota di senso il progetto: Verto usa
le **griglie ufficiali IGM**, che PROJ-senza-griglie non replica. Lo scarto è
documentato in `LOG.md` e `docs/evaluation.md` (0.1–2.8 m). Quel divario è
l'intera ragione per cui questa feature passa da Verto.

### Posizionamento rispetto a `batch`/`geojson` esistenti

Non è un duplicato di `batch`. È un'**estensione**:

- `batch` oggi: legge CSV (colonne E/N), converte, output `table/json/jsonl/csv`
  o GeoJSON costruito a mano.
- nuovo: input più ampio (CSV "sporco", JSON, Parquet via DuckDB) e soprattutto
  **output GIS reale** (GPKG/FGB/SHP/GeoParquet) con CRS embedded — cosa che oggi
  openverto non sa fare.

### Architettura (il pezzo non banale sta in mezzo)

Non è una singola pipeline SQL. È:

```
DuckDB read  →  estrai X/Y  →  Verto convert (riusa chunking/bisezione di batch)
             →  re-join delle coord convertite preservando TUTTI gli attributi
                e l'ordine delle righe  →  DuckDB COPY TO (formato spaziale)
```

Il **re-join / preservazione attributi** in mezzo è la parte ingegneristica vera.
`batch` + `rows_to_geojson` già fanno una parte di questo lavoro e sono il punto
di partenza.

### Decisioni (2026-06-08)

- **Dipendenza**: DuckDB entra come **dipendenza core** (scelta dell'autore).
  Nota: il core passa da 4 dipendenze pure-Python a includere un binario pesante;
  install più pesante per tutti, ma feature sempre disponibile. Da rivalutare se
  l'impatto sull'install/wheel risulta eccessivo.
- **Comando**: **nuovo comando dedicato** (`export`/`spatial`), non estensione di
  `batch`. Tiene `batch` semplice e separa le responsabilità.
- **Output**: GPKG, FlatGeobuf, GeoParquet, Shapefile (tutti e quattro al primo
  giro). GPKG come default naturale.
- **Input**: **solo CSV** al primo giro (lettura robusta via DuckDB: autodetect
  delimitatori/tipi). JSON e Parquet rimandati a iterazioni successive.

### Domande ancora aperte

- Nome esatto del comando: `export` vs `spatial` vs altro.
- Shapefile: gestione limiti noti (nomi campo ≤10 char, tipi) — troncamento
  automatico con warning?
- Default driver dedotto dall'estensione del file di output (`.gpkg`→GPKG, ecc.)?
