---
name: release
description: Publish a new openverto patch release to PyPI, following docs/release.md end to end. User-invocable only.
disable-model-invocation: true
license: MIT
---

# Release openverto

Esegue la procedura di `docs/release.md`. Quel documento resta la fonte di
verita': se qui e la' divergono, vale il documento, e questa skill va corretta.

> **Lo step 8 e irreversibile.** Un numero di versione su PyPI non si puo'
> riusare, nemmeno cancellando la release. Prima di arrivarci, chiedere conferma
> esplicita all'utente. Tutto cio' che viene prima e' recuperabile.

## Prima di cominciare

Fermarsi e riferire all'utente, senza proseguire, se una di queste non regge:

- `git status --short` pulito e `main` aggiornato (`git pull`)
- `twine` disponibile e credenziali presenti (`~/.pypirc`, oppure
  `TWINE_USERNAME`/`TWINE_PASSWORD`)
- `gh auth status` autenticato

## Passi

1. **Versione.** Bump di `version` in `pyproject.toml`. Se un PR mergiato l'ha
   gia' fatto, non rifarlo: passare al punto 2, che e' proprio quello che si
   salta in questo caso.

2. **Lockfile.** `uv lock`, poi **verificare** che sia cambiato:

   ```bash
   grep -A1 'name = "openverto"' uv.lock   # deve stampare la nuova versione
   ```

   `uv.lock` pinna la versione di openverto stesso, quindi va rifatto a ogni
   bump. Un hook di progetto lo segnala, ma non sostituisce questo controllo.

3. **`LOG.md`.** Voce nuova in cima, data `YYYY-MM-DD`, punti brevi e densi.
   Dire cosa cambia per chi usa lo strumento, non cosa si e' toccato.

4. **Lint e test.** Devono passare tutti e tre prima di qualunque passo di
   pubblicazione. Se uno fallisce, fermarsi e riferire:

   ```bash
   uv run ruff check src/ tests/
   uv run pytest              # suite offline
   uv run pytest -m live      # contro il servizio IGM reale
   ```

   I test live non sono opzionali. Il guasto della v0.2.4 era invisibile alla
   suite offline, che mocka `post`, ed e' esattamente cio' che i live vedono.

5. **Commit e tag.** `git add -u`, commit `chore: bump version to vX.Y.Z`
   (saltare il commit se non c'e' nulla in staged), poi `git tag vX.Y.Z`.

6. **Push.** `git push origin main --tags`.

7. **Release su GitHub.** `gh release create vX.Y.Z --title "vX.Y.Z" --notes ...`
   Note in italiano, come `LOG.md`: cosa era rotto, cosa cambia per chi usa lo
   strumento.

8. **Build, check, pubblicazione.** Qui serve la conferma dell'utente.

   ```bash
   uv build
   twine check dist/openverto-X.Y.Z*
   twine upload dist/openverto-X.Y.Z*
   ```

9. **Installazione locale.** `uv tool install --editable . --force`

10. **Verificare cosa ricevono gli utenti.**

    ```bash
    curl -sS https://pypi.org/pypi/openverto/json | jq -r .info.version
    openverto --version
    ```

11. **Smoke test.** Una conversione vera a cache vuota:

    ```bash
    OPENVERTO_CACHE_DIR=$(mktemp -d) openverto convert --from 4265 --to 6706 11.2558 43.7696
    ```

    Deve uscire 0 e stampare coordinate. `mktemp -d` e' cio' che rende reale il
    controllo: forza un cache miss, quindi la richiesta arriva davvero al
    servizio. `--version` prova solo l'installazione.

## Alla fine

Riferire all'utente, con i link: tag, release su GitHub, pagina PyPI, versione
locale, esito dello smoke test. Dire esplicitamente se qualche passo e' stato
saltato e perche'.
