"""Convert path: chunking, bisection-skip, and cache — with a fake poster."""

from __future__ import annotations

import openverto.transform as convmod
from openverto.transform import convert, convert_skipping


class FakePoster:
    """Echoes conversions with a fixed offset; rejects coords whose e == 999."""

    def __init__(self):
        self.calls = 0

    def __call__(self, body):
        self.calls += 1
        coords = body["coordinate"]
        for c in coords:
            if c["e"] == 999:
                return {"stato": "errore", "dove": "Proj", "messaggio": "outside grid"}
        return {
            "stato": "successo",
            "coordinate": [{"e": c["e"] + 0.001, "n": c["n"] + 0.002} for c in coords],
        }


def test_convert_basic(monkeypatch):
    fake = FakePoster()
    monkeypatch.setattr(convmod, "post", fake)
    out = convert([(10, 20), (11, 21)], 4265, 6706, use_cache=False)
    assert out == [(10.001, 20.002), (11.001, 21.002)]
    assert fake.calls == 1


def test_convert_chunks(monkeypatch):
    fake = FakePoster()
    monkeypatch.setattr(convmod, "post", fake)
    monkeypatch.setattr(convmod, "MAX_COORD", 2)
    coords = [(i, i) for i in range(5)]
    out = convert(coords, 4265, 6706, use_cache=False)
    assert len(out) == 5
    assert fake.calls == 3  # 2 + 2 + 1


def test_convert_skipping_isolates_offender(monkeypatch):
    fake = FakePoster()
    monkeypatch.setattr(convmod, "post", fake)
    coords = [(10, 20), (999, 0), (11, 21)]  # middle one is out of grid
    results, skipped = convert_skipping(coords, 4265, 6706)
    assert skipped == [1]
    assert results[0] == (10.001, 20.002)
    assert results[1] is None
    assert results[2] == (11.001, 21.002)


def test_convert_uses_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENVERTO_CACHE_DIR", str(tmp_path))
    fake = FakePoster()
    monkeypatch.setattr(convmod, "post", fake)
    convert([(10, 20)], 4265, 6706, use_cache=True)
    assert fake.calls == 1
    # Second call with the same coordinate must hit the cache (no new request).
    convert([(10, 20)], 4265, 6706, use_cache=True)
    assert fake.calls == 1


def test_roundtrip_residual_zero(monkeypatch):
    """A perfectly invertible fake transform yields ~0 residual."""

    def invertible(body):
        coords = body["coordinate"]
        # forward adds 1; the back call (swapped epsg) must subtract 1.
        delta = 1 if body["inEpsg"] == 3003 else -1
        return {
            "stato": "successo",
            "coordinate": [{"e": c["e"] + delta, "n": c["n"] + delta} for c in coords],
        }

    monkeypatch.setattr(convmod, "post", invertible)
    rep = convmod.roundtrip([(1500000, 4640000)], 3003, 6707, use_cache=False)
    assert rep["max_residual_m"] == 0.0
    assert rep["source_unit"] == "metre"
