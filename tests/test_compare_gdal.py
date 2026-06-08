"""Cross-check openverto (official IGM NTv2 grid) against gdaltransform
(gridless Helmert/towgs84 approximation).

This is a sanity guard, NOT an accuracy test: PROJ's default transforms differ
from the IGM grid by the expected datum uncertainty (sub-metre to a few metres).
A gross discrepancy (tens of metres) would signal a real bug — swapped axes, the
wrong datum, or a zone/false-easting mistake. Skipped when GDAL is absent or
offline; run with ``pytest -m live``.
"""

from __future__ import annotations

import math
import shutil
import subprocess

import pytest

import openverto as ov

pytestmark = pytest.mark.live

# (label, e, n, from_epsg, to_epsg, geographic)
CASES = [
    ("Roma40 geo -> RDN2008 geo", 12.4924, 41.8902, 4265, 6706, True),
    ("GB-Ovest -> RDN2008/TM32", 1514000, 5034000, 3003, 6707, False),
    ("ED50 geo -> RDN2008 geo", 12.49, 41.89, 4230, 6706, True),
    ("ED50/UTM33 -> RDN2008/TM33", 290000, 4640000, 23033, 6708, False),
    ("IGM95 geo -> RDN2008 geo", 12.49, 41.89, 4670, 6706, True),
]

# Generous threshold: well above the real datum-model gap (~3 m for ED50),
# far below what an axis swap or wrong datum would produce (50-200 m+).
MAX_DELTA_M = 10.0


def _gdal(e, n, s, t):
    out = subprocess.run(
        ["gdaltransform", "-s_srs", f"EPSG:{s}", "-t_srs", f"EPSG:{t}"],
        input=f"{e} {n}\n",
        capture_output=True,
        text=True,
    ).stdout.split()
    return float(out[0]), float(out[1])


def _metres(a, b, geographic):
    de, dn = b[0] - a[0], b[1] - a[1]
    if geographic:
        lat = math.radians((a[1] + b[1]) / 2)
        return math.hypot(de * 111320 * math.cos(lat), dn * 110540)
    return math.hypot(de, dn)


@pytest.mark.skipif(shutil.which("gdaltransform") is None, reason="GDAL not installed")
@pytest.mark.parametrize("label,e,n,s,t,geo", CASES, ids=[c[0] for c in CASES])
def test_no_gross_divergence_from_gdal(label, e, n, s, t, geo):
    ours = ov.convert([(e, n)], s, t, use_cache=False)[0]
    theirs = _gdal(e, n, s, t)
    delta = _metres(ours, theirs, geo)
    assert delta < MAX_DELTA_M, f"{label}: {delta:.2f} m gap (openverto={ours}, gdal={theirs})"
