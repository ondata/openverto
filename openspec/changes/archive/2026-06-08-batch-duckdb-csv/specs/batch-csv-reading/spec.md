## ADDED Requirements

### Requirement: Lettura CSV robusta via DuckDB

Il comando `batch` SHALL leggere il file CSV di input tramite DuckDB, con
autodetect del delimitatore, restituendo header e righe nella stessa forma oggi
consumata dal comando.

#### Scenario: Delimitatore punto e virgola

- **WHEN** il CSV usa `;` come delimitatore
- **THEN** `batch` lo legge correttamente senza che l'utente debba dichiarare il
  delimitatore

#### Scenario: Delimitatore virgola standard

- **WHEN** il CSV usa `,` come delimitatore
- **THEN** `batch` continua a leggerlo come prima

### Requirement: Separatore decimale configurabile

Il comando `batch` SHALL permettere all'utente di indicare il separatore decimale
delle colonne numeriche, con default il punto.

#### Scenario: Separatore decimale virgola

- **WHEN** l'utente indica la virgola come separatore decimale e le colonne X/Y
  contengono valori come `12,4924`
- **THEN** `batch` interpreta quei valori come numeri e li converte correttamente

#### Scenario: Default punto decimale

- **WHEN** l'utente non indica alcun separatore decimale
- **THEN** `batch` usa il punto come separatore, preservando il comportamento
  attuale

### Requirement: Comportamento di output invariato

Il comando `batch` SHALL mantenere invariati la risoluzione delle colonne X/Y
(per nome o alias), la gestione delle coordinate fuori griglia (`--skip-invalid`)
e i formati di output esistenti (csv con `e_out`/`n_out`, geojson).

#### Scenario: Colonna inesistente

- **WHEN** l'utente indica un nome di colonna X o Y non presente nell'header
- **THEN** `batch` termina con errore elencando le colonne disponibili, come oggi

#### Scenario: Output CSV invariato

- **WHEN** `batch` produce output CSV
- **THEN** le colonne sono quelle dell'input più `e_out` e `n_out`, identiche al
  comportamento precedente
