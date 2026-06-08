## Why

Il comando `batch` legge oggi il CSV con un `csv.reader` semplice: niente
autodetect del delimitatore e nessuna gestione del separatore decimale. I CSV
italiani/PA usano spessissimo `;` come delimitatore e la virgola come separatore
decimale (es. `12,4924`), che oggi finiscono interpretati come testo e fanno
fallire la conversione. Usare DuckDB per la lettura risolve entrambi i casi con
uno sniffer robusto.

## What Changes

- `batch` legge il CSV tramite DuckDB (`read_csv_auto`) invece del `csv.reader`.
- **Autodetect del delimitatore**: `,`, `;`, tab riconosciuti senza che l'utente
  li dichiari.
- Nuova opzione per indicare il **separatore decimale** (es. virgola), così le
  colonne X/Y con `12,4924` vengono lette come numeri.
- DuckDB entra come **dipendenza core**.
- Nessun comando nuovo. Nessun formato spaziale. L'output di `batch`
  (`e_out`/`n_out`, csv/geojson) resta invariato.

## Capabilities

### New Capabilities

- `batch-csv-reading`: lettura robusta del CSV di input del comando `batch` via
  DuckDB, con autodetect del delimitatore e separatore decimale configurabile,
  preservando l'attuale risoluzione delle colonne e l'output.

### Modified Capabilities

<!-- Nessuna: non esistono spec in openspec/specs/. Il comportamento di output di batch non cambia. -->

## Impact

- **Dipendenze**: aggiunta di `duckdb` alle dipendenze core in `pyproject.toml`.
- **Codice**: `src/openverto/geo.py` (`read_csv_file`) o un nuovo helper di
  lettura passa a DuckDB; il comando `batch` in `src/openverto/cli.py` ottiene
  l'opzione separatore decimale. La logica di conversione/skip resta invariata.
- **Test**: nuovi test offline su delimitatore non standard e separatore
  decimale virgola.
