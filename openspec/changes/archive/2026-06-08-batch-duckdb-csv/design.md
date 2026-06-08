## Context

Il comando `batch` (`src/openverto/cli.py`) legge il CSV via
`read_csv_file` in `geo.py`, che usa `csv.reader` e tratta ogni cella come
stringa. Le colonne X/Y vengono poi convertite con `float(rec[idx].strip())`.
Questo fallisce su due casi molto comuni nei dati italiani: delimitatore `;` e
separatore decimale virgola (`12,4924`).

DuckDB è ora una dipendenza del progetto e il suo `read_csv_auto` ha uno sniffer
robusto che riconosce delimitatore e tipi, con un parametro esplicito per il
separatore decimale.

## Goals / Non-Goals

**Goals:**

- `batch` legge il CSV via DuckDB con autodetect del delimitatore.
- Opzione per dichiarare il separatore decimale (default `.`, tipico alternativo
  `,`).
- Le colonne X/Y diventano numeriche già in lettura (niente `float()` su stringhe
  con virgola).

**Non-Goals:**

- Nessun formato di output spaziale (GPKG/FGB/SHP/GeoParquet): abbandonati.
- Nessun comando nuovo: si potenzia `batch`.
- Nessun cambiamento all'output di `batch` (`e_out`/`n_out`, csv/geojson).
- Nessun input non-CSV (JSON/Parquet) per ora.

## Decisions

**1. Lettura via `read_csv_auto`, restituendo `(header, records)` come oggi.**
Il nuovo helper interroga DuckDB e produce la stessa struttura
`(list[str], list[list[str]])` che `batch` già consuma, così a valle non cambia
nulla (risoluzione colonne, skip, output). *Alternativa scartata*: riscrivere
l'intera pipeline di `batch` in SQL — sovradimensionato e rischioso.

**2. Separatore decimale come opzione esplicita, non autodetect.**
DuckDB non indovina in modo affidabile la virgola decimale (ambigua col
delimitatore). Si espone `--decimal` (default `.`) passato a `read_csv_auto`
come `decimal_separator`. *Alternativa scartata*: euristica lato Python —
fragile.

**3. DuckDB sniffer al posto di `csv.Sniffer`.**
Scelta dell'autore: usare DuckDB che è già una dipendenza e ha uno sniffer
migliore. *Alternativa scartata*: `csv.Sniffer` + `str.replace(',', '.')` —
eviterebbe la dipendenza ma è meno robusto e contro la richiesta esplicita.

**4. Le celle restano restituite come stringhe verso `batch`.**
Per non toccare l'output, il record passa a `batch` come stringhe; le sole
colonne che contano numericamente (X/Y) sono garantite parse-abili perché
DuckDB le ha già normalizzate (punto decimale) in lettura.

## Risks / Trade-offs

- **[Tipi vs stringhe] DuckDB tipizza, `batch` vuole stringhe** → si converte il
  risultato DuckDB in stringhe preservando il valore; per i numeri si usa una
  rappresentazione con punto decimale, così `float()` a valle non fallisce.
- **[Peso dipendenza] DuckDB binario ~20 MB solo per leggere CSV** → accettato
  esplicitamente dall'autore; lo sniffer robusto e l'uso già presente di DuckDB
  giustificano la scelta.
- **[NULL/celle vuote] DuckDB rende NULL le celle vuote** → mappare i NULL a
  stringa vuota per non alterare l'output rispetto a oggi.
