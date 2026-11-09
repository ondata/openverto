"""HTTP layer for the IGM Verto Online service.

The service is a single POST endpoint discriminated by the body field
``richiesta``: ``"info"`` lists the supported reference systems, ``"conversione"``
transforms an array of ``{e, n}`` coordinates between two EPSG codes. Conversions
carry the ``utente``/``chiave`` credentials issued by IGM (see
:func:`get_credentials`).

Service-level errors are returned inside an HTTP 200 body as
``{"stato": "errore", "dove": ..., "messaggio": ...}`` and surface as
:class:`VertoError`.
"""

from __future__ import annotations

import json
import os
import time

import httpx

#: Default endpoint (relative path ``/volapi`` is already included).
DEFAULT_BASE_URL = "https://igmi.esercito.difesa.it/porta-magna/wps/volapi"

#: Maximum number of coordinates accepted per ``conversione`` request.
MAX_COORD = 32000

_USER_AGENT = "openverto"

#: Sent when no credentials are configured. IGM announced mandatory credentials
#: from 2026-11-01, but on 2026-11-06 the service still accepts any value.
_PLACEHOLDER_CREDENTIAL = "openverto"

#: Message shown when the service rejects the credentials.
CREDENTIALS_HINT = (
    "Le credenziali IGM sono gratuite: accedi al sito IGM, Area Riservata > "
    "'Abbonamenti ai servizi', e usa l'email come utente e la 'Chiave di Accesso' "
    "come chiave. Scadono ogni 3 mesi. Impostale con OPENVERTO_UTENTE e "
    "OPENVERTO_CHIAVE, oppure con --utente e --chiave."
)

# Module-level configuration (mutable via the setters below).
_base_url = DEFAULT_BASE_URL
_timeout = 30.0
_verify_ssl = True
_extra_headers: dict[str, str] = {}
_utente: str | None = None
_chiave: str | None = None

#: Seconds to pause BETWEEN consecutive conversion batches when a single job
#: spans more than one request (i.e. more than MAX_COORD coordinates). The IGM
#: service is free — be a good citizen and don't hammer it. A single
#: batch (<= MAX_COORD) is never delayed. Set to 0 to disable.
_throttle = 2.0


def set_base_url(url: str) -> None:
    """Override the service endpoint (useful for tests or a mirror)."""
    global _base_url
    _base_url = url


def get_base_url() -> str:
    return _base_url


def set_timeout(seconds: float) -> None:
    """Set the per-request timeout in seconds."""
    global _timeout
    _timeout = float(seconds)


def get_timeout() -> float:
    return _timeout


def set_verify_ssl(verify: bool) -> None:
    """Enable TLS certificate verification (default True).

    Disabling verification allows server impersonation; use only explicitly
    when accepting that risk, including for any credentials sent.
    """
    global _verify_ssl
    _verify_ssl = verify


def set_throttle(seconds: float) -> None:
    """Set the pause between conversion batches for multi-batch jobs (seconds).

    Defaults to 2 s to avoid hammering the free IGM service. Only applies when a
    job spans more than one request (> MAX_COORD coordinates). Pass 0 to disable.
    """
    global _throttle
    _throttle = max(0.0, float(seconds))


def get_throttle() -> float:
    return _throttle


def set_extra_headers(headers: dict[str, str]) -> None:
    """Replace the static extra HTTP headers sent with every request."""
    global _extra_headers
    _extra_headers = dict(headers)


def get_extra_headers() -> dict[str, str]:
    return dict(_extra_headers)


def set_credentials(utente: str | None = None, chiave: str | None = None) -> None:
    """Set the IGM credentials, overriding the environment. ``None`` clears a field."""
    global _utente, _chiave
    _utente, _chiave = utente, chiave


def get_credentials() -> tuple[str, str]:
    """Return ``(utente, chiave)`` to send with a conversion.

    Each field comes from :func:`set_credentials`, then from ``OPENVERTO_UTENTE``
    / ``OPENVERTO_CHIAVE``, then from a placeholder.
    """
    return (
        _utente or os.environ.get("OPENVERTO_UTENTE") or _PLACEHOLDER_CREDENTIAL,
        _chiave or os.environ.get("OPENVERTO_CHIAVE") or _PLACEHOLDER_CREDENTIAL,
    )


class VertoError(Exception):
    """A service-level error reported by Verto Online (``stato: errore``).

    The most common case is an out-of-grid coordinate, signalled by
    ``dove == "Proj"`` (the underlying PROJ transform rejecting a coordinate
    outside the IGM grid coverage).
    """

    def __init__(self, messaggio: str, dove: str = ""):
        self.messaggio = messaggio
        self.dove = dove
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.dove:
            return f"verto service error ({self.dove}): {self.messaggio}"
        return f"verto service error: {self.messaggio}"

    @property
    def outside_grid(self) -> bool:
        """Whether this is the 'coordinate outside the IGM grid coverage' case."""
        if self.dove.strip().lower() == "proj":
            return True
        m = (self.messaggio or "").lower()
        return "outside grid" in m or "griglia" in m

    @property
    def credentials_rejected(self) -> bool:
        """Whether the service refused ``utente``/``chiave``.

        The wording of a rejection is unknown until IGM turns the check on, so
        this matches the field name (``dove: utente`` is what a missing field
        returns today) and the words a rejection is likely to use.
        """
        if self.dove.strip().lower() in ("utente", "chiave"):
            return True
        m = (self.messaggio or "").lower()
        return any(w in m for w in ("utente", "chiave", "credenzial", "abbonament", "autorizz"))


def _salvage_json(text: str) -> dict | None:
    """Extract the first JSON object from a body polluted by extra output.

    Returns ``None`` when nothing parseable is found, so the caller can keep
    raising its original diagnostic.
    """
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def post(body: dict, *, retries: int = 2) -> dict:
    """POST a request body to the Verto endpoint and return the parsed JSON.

    Retries transient network/5xx errors with a short backoff. Raises
    :class:`httpx.HTTPError` on a non-recoverable transport error and
    :class:`ValueError` on an unparseable body. Service-level ``stato: errore``
    bodies are returned as-is for the caller to interpret.
    """
    headers = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
    headers.update(_extra_headers)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=_timeout, verify=_verify_ssl) as client:
                resp = client.post(_base_url, json=body, headers=headers)
            if resp.status_code in (401, 403):
                raise VertoError(f"credenziali rifiutate (HTTP {resp.status_code})", "chiave")
            if resp.status_code >= 500 and attempt < retries:
                last_exc = httpx.HTTPStatusError(
                    f"server error {resp.status_code}", request=resp.request, response=resp
                )
                time.sleep(0.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError as exc:
                # The service has been observed prefixing the JSON body with a
                # stray debug line (e.g. "QUERY: INSERT INTO vol.log ..."), which
                # makes a strict parse fail. Recover the first JSON object in the
                # body, tolerating junk before and after it.
                salvaged = _salvage_json(resp.text)
                if salvaged is not None:
                    return salvaged
                raise ValueError(f"invalid JSON from Verto service: {exc}") from exc
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    # Unreachable, but keeps type-checkers happy.
    raise last_exc if last_exc else RuntimeError("post failed")
