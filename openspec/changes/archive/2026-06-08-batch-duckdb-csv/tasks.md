## 1. Dipendenza

- [x] 1.1 Aggiungere `duckdb` alle dipendenze core in `pyproject.toml` e aggiornare `uv.lock`

## 2. Lettura CSV via DuckDB

- [x] 2.1 Implementare un helper di lettura che usa `read_csv` (delimitatore rilevato dall'header) e restituisce `(header, records)` come stringhe, mappando i NULL a stringa vuota
- [x] 2.2 Supportare il parametro separatore decimale (`decimal_separator`) con default `.`
- [x] 2.3 Integrare l'helper in `read_csv_file`/`batch` senza cambiare la struttura dati a valle
- [x] 2.4 Supportare `-` come input da stdin (materializzazione su file temporaneo)

## 3. CLI

- [x] 3.1 Aggiungere a `batch` l'opzione `--decimal` (default `.`)
- [x] 3.2 Aggiornare il docstring/Examples di `batch` con un esempio `;` + virgola decimale, stdin e il formato di default

## 4. Test e documentazione

- [x] 4.1 Test offline: CSV con delimitatore `;` letto correttamente
- [x] 4.2 Test offline: separatore decimale virgola sulle colonne X/Y + header tutto-numerico (regression sniffer) + stdin
- [x] 4.3 Test offline: risoluzione colonne per alias/nome e colonna mancante
- [x] 4.4 Aggiornare README (formato di default + dipendenza DuckDB + esempi), help di `batch`, skill `verto-explorer`, guida install skill e `LOG.md`
- [x] 4.5 Verificare `ruff` pulito e build wheel ok
