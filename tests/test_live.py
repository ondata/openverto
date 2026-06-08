"""Live integration tests against the IGM Verto Online service.

Skippable offline / in CI: run with ``pytest -m live`` to include them.
"""

from __future__ import annotations

import pytest

import openverto as ov

pytestmark = pytest.mark.live


def test_live_systems():
    rows = ov.systems(refresh=True)
    assert len(rows) == 20
    assert any(r["epsg"] == 6706 for r in rows)


def test_live_convert_golden():
    # Roma40 geographic -> RDN2008 geographic, Rome reference point.
    out = ov.convert([(12.4924, 41.8902)], 4265, 6706, use_cache=False)
    assert out[0][0] == pytest.approx(12.4921961827, abs=1e-7)
    assert out[0][1] == pytest.approx(41.8908506304, abs=1e-7)


def test_live_sea_coordinate_is_valid():
    # A point in the Tyrrhenian Sea, near Italy: covered by the IGM grid.
    out = ov.convert([(11.0, 40.0)], 4265, 6706, use_cache=False)
    assert out[0][0] == pytest.approx(11.0, abs=0.01)


def test_live_outside_italy_rejected():
    # Paris: outside the grid coverage.
    with pytest.raises(ov.VertoError) as exc:
        ov.convert([(2.35, 48.85)], 4265, 6706, use_cache=False)
    assert exc.value.outside_grid
