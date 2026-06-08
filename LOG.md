# LOG

## 2026-06-08

- Porting Python del CLI Go `printing-press/library/verto` → **openverto** (libreria + CLI, stile `opensdmx`).
- Architettura `src/openverto/`: `base` (HTTP + `VertoError`), `refdata` (tabella statica 20 EPSG), `systems` (endpoint `info` + cache), `transform` (convert/chunking/bisezione, inspect/targets/roundtrip), `detect` (euristica offline), `cache` (write-through), `geo` (GeoJSON + CSV batch), `cli` (typer).
- Output globale `-o/--output table|json|jsonl|csv` (jsonl ideale per coordinate).
- Verificato sul servizio live IGM: valore golden `4265→6706 (12.4924,41.8902)` esatto; **coordinate a mare** vicino all'Italia (Tirreno) valide; **fuori Italia** (Parigi/oceano) → `errore/Proj/outside grid`.
- Gestione errori fuori-griglia con hint in italiano + suggerimento `--skip-invalid` in batch per isolare i punti fuori Italia.
- Fix collisione di nome modulo `convert` ↔ funzione `convert`: rinominato modulo in `transform.py`.
- Test: 20 offline (refdata/detect/chunking/bisezione/cache/geojson-int) + 4 live skippable (`-m live`). Ruff pulito. Build wheel ok.
- TODO: repo su GitHub `ondata`; eventuale Agent Skill; pubblicazione PyPI.
