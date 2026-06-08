# Evaluation

## Cross-check vs gdaltransform (2026-06-08)

Goal: confirm openverto (which uses the **official IGM Verto Online** service,
backed by the authoritative NTv2 grids) has no gross errors — swapped axes,
wrong datum, or zone/false-easting mistakes — by comparing it against
`gdaltransform` (GDAL 3.11 / PROJ 9.6), which uses a **gridless**
Helmert/`towgs84` approximation.

Sub-metre to a few-metre differences are **expected and correct**: that gap is
the datum-model uncertainty PROJ carries without the IGM grids. A discrepancy of
tens of metres would instead reveal a real bug.

| Conversion | openverto | gdal (no grid) | Δ (m) |
|---|---|---|---|
| Roma40 geo → RDN2008 geo (Roma) | 12.4922, 41.8909 | 12.4922, 41.8908 | **1.65** |
| GB-Ovest → RDN2008/TM32 (Milano) | 513973.034, 5033980.214 | 513972.025, 5033979.991 | **1.03** |
| ED50 geo → RDN2008 geo | 12.4891, 41.889 | 12.4891, 41.889 | **2.80** |
| ED50/UTM33 → RDN2008/TM33 (Roma) | 289931.002, 4639807.796 | 289929.465, 4639810.128 | **2.79** |
| IGM95 geo → RDN2008 geo | 12.49, 41.89 | 12.49, 41.89 | **0.11** |
| GB-Est → RDN2008/TM33 (Bari) | 539990.837, 4539993.425 | 539991.758, 4539992.378 | **1.40** |

### Reading of the results

- **No gross errors.** All deltas are 0.1–2.8 m. An axis swap or wrong datum
  would land 50–200 m off (or in the sea); none did.
- **IGM95 → RDN2008 = 0.11 m.** Both are ETRS89 realizations (ETRF89 vs
  ETRF2000), so the transform should be near-zero — it is. This is the strongest
  signal that openverto applies the correct datum and axis order.
- **ED50 shows the largest gap (~2.8 m).** Expected: ED50→ETRF datum
  parameters are the least well constrained, and the IGM grid encodes local
  distortions PROJ's single Helmert block cannot.
- **Roma40 / Gauss-Boaga ~1–1.7 m.** Consistent with the known Roma40→ETRF2000
  grid-vs-Helmert difference over Italy.

### Conclusion

openverto's results match the official IGM transform and diverge from gridless
PROJ only by the expected datum uncertainty. Use openverto when you need the
**authoritative** Italian transform (cadastre, official open data); a gridless
tool like ogr2ogr is fine only where 1–3 m of datum error is acceptable.

Regression guard: `tests/test_compare_gdal.py` (run with `pytest -m live`)
asserts the gap stays under 10 m for representative cases.
