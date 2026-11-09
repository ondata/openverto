# openverto

[![PyPI version](https://img.shields.io/pypi/v/openverto)](https://pypi.org/project/openverto/)
[![GitHub](https://img.shields.io/badge/github-ondata%2Fopenverto-blue?logo=github)](https://github.com/ondata/openverto)
[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/ondata/openverto)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Newsletter](https://img.shields.io/badge/newsletter-ondata-FF6719?logo=substack)](https://ondata.substack.com/)

> Tool sperimentale — aiutaci a testarlo [aprendo issue](https://github.com/ondata/openverto/issues) o inviando feedback.

CLI e libreria Python per il servizio ufficiale **[IGM Verto Online](https://igmi.esercito.difesa.it/servizi/verto-online/)**: trasforma coordinate tra tutti i sistemi di riferimento italiani (Roma40, ED50, IGM95, ETRS89, RDN2008) **senza installare le griglie NTv2**, appoggiandosi al servizio autorevole dell'Istituto Geografico Militare.

Pensato per essere **orchestrato da agenti AI**: output `--json`/`--jsonl`/`--csv`, non interattivo, pipeable, read-only. L'intelligenza sugli EPSG (`inspect`, `detect`, `targets`) è completamente **offline**.

> **Con un'AI.** openverto può essere usato anche tramite un AI, che leggerà il suo help per capirne il funzionamento. Il repo include anche la Agent Skill [`verto-explorer`](skills/verto-explorer/SKILL.md), che si [installa così](docs/skill/README.md).


## Installazione

Come strumento CLI (consigliato):

```bash
uv tool install openverto
```

> Se non hai `uv`, consulta la [guida di installazione](https://docs.astral.sh/uv/getting-started/installation/).

oppure con pip:

```bash
pip install openverto
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

# converti un CSV di punti Gauss-Boaga (colonne est/nord) in RDN2008/UTM32
openverto batch catasto.csv --from 3003 --to 7791 --e-col est --n-col nord --out out.csv

# CSV all'italiana (delimitatore ; e virgola decimale), da stdin verso stdout
cat comuni.csv | openverto batch - --from 4265 --to 6706 --decimal , --e-col lon --n-col lat

# riproietta le geometrie di un GeoJSON
openverto geojson aree.geojson --from 4230 --to 6706 --out out.geojson
```

### Certificato SSL

La verifica del certificato TLS è sempre attiva per default. Se il certificato
IGM è scaduto, puoi saltare esplicitamente il controllo con `--insecure` (o `-k`),
prima del sottocomando:

```bash
openverto --insecure convert --from 4265 --to 6706 --no-cache 12.4924 41.8902
```

**Attenzione:** lo skip non verifica l'identità del server e consente attacchi
di impersonificazione, anche alle credenziali inviate. Usalo solo se accetti
questo rischio; non viene mai attivato automaticamente dopo un errore SSL.

### Griglie di spostamento (`grid`)

`grid` costruisce una griglia di spostamento orizzontale fra due sistemi geografici, campionando Verto Online sui nodi di un reticolo regolare. Il risultato è un GeoTIFF nel [formato griglie di PROJ](https://proj.org/en/stable/specifications/geodetictiffgrids.html), che GDAL e PROJ usano per convertire punti e raster senza chiamare il servizio.

**Le griglie sono solo 2D.** Verto Online converte coordinate planimetriche: la griglia contiene gli spostamenti in latitudine e longitudine, e le quote non vengono trasformate.

```bash
# nodi, richieste e tempo previsti, senza chiamare il servizio
openverto grid --from 4265 --to 6706 --bbox 11 43.5 12 44 --dry-run

# la griglia, con passo predefinito 7,5' x 5' (450" x 300")
openverto grid --from 4265 --to 6706 --bbox 11 43.5 12 44 --out roma40_rdn2008.tif
```

Il comando accetta solo sistemi geografici disponibili in Verto, di datum diversi: 4265 (Roma40), 4230 (ED50), 4670 (IGM95), 6706 (RDN2008). Accanto alla griglia scrive `<out>.report.json`, con nodi totali, validi e in errore e richieste fatte.

Il rettangolo deve stare tutto dentro la copertura di Verto: un solo nodo fuori fa fallire la richiesta, e in quel caso non viene scritta nessuna griglia. Il rettangolo 6 35 19 47,5 sull'Italia intera viene rifiutato (prova del 9 novembre 2026). Si usa quindi un `--bbox` più piccolo, che copra l'area di lavoro.

Con il passo predefinito i nodi coincidono con quelli dei grigliati IGM: multipli di 7,5' dal meridiano di Monte Mario (12°27'08,4" E) e di 5' in latitudine. Su 300 punti fra i nodi, in Italia centrale, la differenza da Verto Online è di 0,09 cm al massimo. Con un reticolo non allineato (`--origin-lon`, `--origin-lat`) sale a 4,35 cm.

#### Riproiettare un raster con la griglia

La griglia deve coprire tutto il raster. Si indica nel sistema di partenza con `+nadgrids`; `+ellps=intl` è l'ellissoide di Roma40 e di ED50.

```bash
# raster in Roma40 geografico (EPSG:4265) -> RDN2008 geografico (EPSG:6706)
gdalwarp \
  -s_srs "+proj=longlat +ellps=intl +nadgrids=$PWD/roma40_rdn2008.tif +no_defs +type=crs" \
  -t_srs EPSG:6706 \
  raster_roma40.tif raster_rdn2008.tif

# raster in Gauss-Boaga fuso Ovest (EPSG:3003) -> RDN2008 / UTM 32N (EPSG:7791)
gdalwarp \
  -s_srs "+proj=tmerc +lat_0=0 +lon_0=9 +k=0.9996 +x_0=1500000 +y_0=0 +ellps=intl +nadgrids=$PWD/roma40_rdn2008.tif +units=m +no_defs +type=crs" \
  -t_srs EPSG:7791 \
  raster_gb.tif raster_utm32.tif

# un punto, per controllo (lon lat)
echo "11.5 43.7 0 0" | cct -d 9 +proj=hgridshift +grids=$PWD/roma40_rdn2008.tif
```

#### Uso del servizio

Verto Online è gratuito e condiviso, quindi il comando fa il minor numero possibile di richieste: una alla volta, con i batch più grandi ammessi da `maxCoord` e una pausa fra l'una e l'altra (`--pause`, 2 secondi). Sopra le 10 richieste serve `--yes`. Le risposte riuscite restano in cache, quindi un'esecuzione interrotta riparte da dove si era fermata. Dopo 3 errori di rete consecutivi il comando si ferma, e una risposta di errore del servizio non viene ritentata.

Questo vale per tutti i comandi e per la libreria: per ogni utente di una macchina parte una sola richiesta alla volta verso IGM. Più esecuzioni in parallelo o più thread si mettono in coda, anche se usano cache diverse. Il blocco non coordina utenti o macchine diversi. Se il file di blocco non si può creare, ad esempio con la home in sola lettura, la richiesta parte lo stesso.

Le [condizioni d'uso](https://igmi.esercito.difesa.it/servizi/verto-online/), lette il 9 novembre 2026, dicono che l'uso delle API è libero purché non comprometta il funzionamento del servizio e non sovraccarichi l'infrastruttura, e che IGM può introdurre limiti e rate limit in qualsiasi momento. Sui risultati dicono che, salvo diversa indicazione, «mantengono la stessa licenza applicabile ai dati in ingresso». Non contengono divieti specifici su uso massivo o dati derivati. Il comando produce la griglia in locale: openverto non ne distribuisce.

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

Tutte le opzioni sono documentate nel [**riferimento CLI completo**](docs/cli.md).

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
| `grid` | Costruisce una griglia di spostamento 2D per GDAL e PROJ campionando Verto Online |
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
results, skipped = ov.convert_skipping(coords, 3003, 7791)

# errore residuo di una catena di datum
ov.roundtrip([(1500000, 4640000)], 3003, 7791)
```

## Credenziali

Il servizio è gratuito, ma IGM ha annunciato che dal 1° novembre 2026 è riservato agli utenti registrati. Al 6 novembre 2026 il controllo non risulta ancora attivo: openverto funziona anche senza credenziali, e conviene impostarle subito.

Si ottengono con un account sul sito IGM, in Area Riservata > "Abbonamenti ai servizi", e scadono ogni 3 mesi. L'utente è l'email dell'account, la chiave è la "Chiave di Accesso":

```bash
export OPENVERTO_UTENTE="nome@esempio.it"
export OPENVERTO_CHIAVE="la-tua-chiave"
```

Passaggi con le schermate in [`docs/cli.md`](docs/cli.md). Dalla libreria si usa `ov.set_credentials(utente, chiave)`.

## Note tecniche

- Le coordinate geografiche sono **sempre in gradi sessadecimali** (in input e in output); le proiettate in **metri**. Dipende dal CRS, non dalla direzione della conversione.
- La conversione IGM è **planimetrica**: le quote **Z/M non vengono trasformate**. openverto le preserva inalterate nei GeoJSON (riproietta solo x/y).
- **Codici RDN2008:** il servizio non accetta più 6707, 6708, 6709 e 6876. Al loro posto si usano 7791, 7792, 7793 e 7795, gli stessi sistemi con assi Est, Nord; con un codice vecchio openverto indica quello da usare.
- Le conversioni **tra sistemi con lo stesso datum** non sono ammesse dal servizio (vedi `targets`).
- Il servizio accetta al massimo **32000 coordinate** per richiesta; `batch` esegue automaticamente il chunking.
- La griglia IGM copre l'Italia e i mari circostanti: coordinate fuori copertura vengono rifiutate (usa `detect`/`inspect` per controllare assi e EPSG).
- **Il servizio IGM è gratuito: non abusarne.** Quando un job supera le **32000 coordinate** (il limite per richiesta) e viene quindi spezzato in più blocchi, openverto mette una pausa di **2 secondi tra un blocco e l'altro** (`--throttle`, o `set_throttle()` nella libreria). Una conversione singola (≤32000) non viene mai rallentata. `--throttle 0` disabilita la pausa, ma usalo con criterio.

## API del servizio IGM

openverto si appoggia all'API pubblica di IGM Verto Online, che non ha una
documentazione OpenAPI ufficiale. Ne abbiamo ricostruita una **non ufficiale**
per reverse engineering, leggibile e con esempi: [`docs/openapi.yaml`](docs/openapi.yaml)
([sfogliala su Redoc](https://redocly.github.io/redoc/?url=https://raw.githubusercontent.com/ondata/openverto/main/docs/openapi.yaml)).

## Disclaimer

openverto è uno strumento **indipendente** e **non ufficiale**: **non** è sviluppato, approvato, certificato o distribuito dall'**Istituto Geografico Militare (IGM)**. Agisce esclusivamente come client verso un endpoint pubblico.

Il software, l'infrastruttura e l'implementazione del servizio restano di esclusiva proprietà dell'IGM. Salvo diversa indicazione, i risultati mantengono la licenza dei dati in ingresso. L'uso del servizio tramite openverto è soggetto alle [condizioni d'uso ufficiali pubblicate da IGM](https://igmi.esercito.difesa.it/servizi/verto-online/); l'invio di coordinate all'endpoint implica l'accettazione di tali condizioni.

## Crediti

Servizio dati: [IGM Verto Online](https://igmi.esercito.difesa.it/servizi/verto-online/), Istituto Geografico Militare.

Il comando `grid` segue il metodo descritto in queste pubblicazioni, con Verto Online come servizio di conversione:

- Sferlazza E., Bellini E. (2008), *Conversione di coordinate con grigliati NTv2 - un'applicazione per il territorio siciliano*.
- Sferlazza E., Falciano A. (2009), *Trasformazione della cartografia catastale mediante grigliati NTv2*, Atti della 13a conferenza ASITA.
- Costabile S., Martini S., Avanzi A., Petriglia L., Corrarello G. (2012), [*Geoportale nazionale - un approfondimento sulle metodologie di conversione e trasformazione coordinate*](https://www.mediageo.it/ojs/index.php/GEOmedia/article/download/229/205/969), GEOmedia 6-2012.
- Sferlazza E. (2014), [*Come costruirsi un grigliato NTv2 in casa*](https://ojs.mediageo.it/index.php/GEOmedia/article/view/797), GEOmedia 2-2014.

## Licenza

MIT.
