"""TLS verification stays enabled unless explicitly disabled."""

import httpx
import pytest
from typer.testing import CliRunner

from openverto import base
from openverto.cli import app


@pytest.fixture
def tls_client(monkeypatch, tmp_path):
    seen = []
    real_client = httpx.Client

    def handler(request):
        return httpx.Response(200, json={"stato": "successo", "coordinate": [{"e": 1, "n": 2}]})

    def client(**kwargs):
        seen.append(kwargs["verify"])
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(base.httpx, "Client", client)
    monkeypatch.setattr(base, "_verify_ssl", True, raising=False)
    monkeypatch.setenv("OPENVERTO_CACHE_DIR", str(tmp_path))
    return seen


def test_post_verifies_ssl_by_default(tls_client):
    base.post({"richiesta": "info"}, retries=0)
    assert tls_client == [True]


@pytest.mark.parametrize("flag", ["--insecure", "-k"])
def test_cli_insecure_is_explicit_and_resets(tls_client, flag):
    runner = CliRunner()
    command = ["convert", "--from", "4265", "--to", "6706", "--no-cache", "12.4924", "41.8902"]
    for options in ([], [flag], []):
        result = runner.invoke(app, options + command)
        assert result.exit_code == 0, result.output
    assert tls_client == [True, False, True]


def test_ssl_failure_never_retries_without_verification(monkeypatch):
    seen = []

    def client(**kwargs):
        seen.append(kwargs["verify"])
        raise httpx.ConnectError("CERTIFICATE_VERIFY_FAILED")

    monkeypatch.setattr(base, "_verify_ssl", True, raising=False)
    monkeypatch.setattr(base.httpx, "Client", client)
    monkeypatch.setattr(base.time, "sleep", lambda _: None)
    with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
        base.post({"richiesta": "info"})
    assert seen == [True, True, True]
