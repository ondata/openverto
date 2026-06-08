# LOG

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
