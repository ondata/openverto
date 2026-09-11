La suite live (`uv run pytest -m live`) ha fallito due volte di seguito, a 60 secondi di distanza, quindi non è un disservizio momentaneo del servizio IGM.

I test live non girano nella CI normale, perché `addopts = "-m 'not live'"` li esclude. Questo controllo schedulato esiste proprio per accorgersi dei cambiamenti lato IGM, che non coincidono con un nostro commit: la v0.2.4 è stata scoperta a mano, giorni dopo.

Cosa guardare, nell'ordine.

Il corpo grezzo di una risposta di conversione, che è dove si è rotto l'ultima volta:

```
curl -H 'Content-Type: application/json' \
  --data '{"richiesta":"conversione","utente":"openverto","chiave":"openverto","inEpsg":4265,"outEpsg":6706,"coordinate":[{"e":13.3123,"n":38.1157}]}' \
  https://igmi.esercito.difesa.it/porta-magna/wps/volapi
```

Se il corpo è sporco o ha cambiato forma, il punto da adattare è `base.post` in `src/openverto/base.py`, unico posto del progetto che parla HTTP.

Se invece sono i numeri a essere cambiati, il test da guardare è `test_live_convert_golden`: va capito se IGM ha aggiornato le griglie, e in quel caso i valori attesi vanno rifatti, non aggirati.

Se è cambiata la forma dell'API, aggiornare anche `docs/openapi.yaml`, che è documentazione ricostruita per reverse engineering e va in deriva in silenzio.

Finché questa issue resta aperta, i controlli successivi la commentano invece di aprirne altre.
