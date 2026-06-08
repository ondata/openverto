"""Curated static reference table for the 20 reference systems Verto supports.

This powers ``inspect``, ``targets`` and ``detect`` with domain knowledge the
API does not expose: datum family (which determines valid conversion targets,
since same-datum conversions are rejected by the service), axis kind, units,
zone, and false easting.

Ported verbatim from the Go ``refdata.go`` table.
"""

from __future__ import annotations

# Datum family identifiers. Same-family conversions are rejected by the service
# ("Le conversioni fra sistemi con lo stesso datum non sono ammesse").
FAMILY_ROMA40 = "Roma40 / Monte Mario"
FAMILY_ED50 = "ED50"
FAMILY_ETRS89 = "ETRS89 / IGM95 (ETRF89)"
FAMILY_RDN2008 = "RDN2008 (ETRF2000)"


def _ref(epsg, name, family, kind, unit, zone, false_easting, notes) -> dict:
    return {
        "epsg": epsg,
        "name": name,
        "datum_family": family,
        "kind": kind,
        "unit": unit,
        "zone": zone,
        "false_easting": false_easting,
        "notes": notes,
    }


# Keyed by EPSG. Descriptions mirror the IGM ``info`` response.
REF_TABLE: dict[int, dict] = {
    # Roma40 / Monte Mario family
    4265: _ref(4265, "Monte Mario", FAMILY_ROMA40, "geographic", "degree", "", "", "Roma40 geographic (Greenwich); e=lon, n=lat in decimal degrees."),
    4806: _ref(4806, "Monte Mario (Rome)", FAMILY_ROMA40, "geographic", "degree", "", "", "Roma40 geographic referred to the Rome (Monte Mario) prime meridian."),
    3003: _ref(3003, "Monte Mario / Italy zone 1", FAMILY_ROMA40, "projected", "metre", "Gauss-Boaga fuso Ovest (zone 1)", "1 500 000 m", "Gauss-Boaga West belt; covers Italy west of ~12°E."),
    3004: _ref(3004, "Monte Mario / Italy zone 2", FAMILY_ROMA40, "projected", "metre", "Gauss-Boaga fuso Est (zone 2)", "2 520 000 m", "Gauss-Boaga East belt; covers Italy east of ~12°E."),

    # ED50 family
    4230: _ref(4230, "ED50", FAMILY_ED50, "geographic", "degree", "", "", "European Datum 1950 geographic; e=lon, n=lat in decimal degrees."),
    23032: _ref(23032, "ED50 / UTM zone 32N", FAMILY_ED50, "projected", "metre", "UTM zone 32N", "500 000 m", "ED50 UTM; 6°E–12°E."),
    23033: _ref(23033, "ED50 / UTM zone 33N", FAMILY_ED50, "projected", "metre", "UTM zone 33N", "500 000 m", "ED50 UTM; 12°E–18°E."),
    23034: _ref(23034, "ED50 / UTM zone 34N", FAMILY_ED50, "projected", "metre", "UTM zone 34N", "500 000 m", "ED50 UTM; 18°E–24°E (eastern Italy / Salento)."),

    # ETRS89 / IGM95 family (ETRF89 realization + pan-European ETRS89 grids)
    4670: _ref(4670, "IGM95", FAMILY_ETRS89, "geographic", "degree", "", "", "ETRS89 (ETRF89) geographic; the IGM95 national network."),
    3064: _ref(3064, "IGM95 / UTM zone 32N", FAMILY_ETRS89, "projected", "metre", "UTM zone 32N", "500 000 m", "ETRS89 UTM; 6°E–12°E."),
    3065: _ref(3065, "IGM95 / UTM zone 33N", FAMILY_ETRS89, "projected", "metre", "UTM zone 33N", "500 000 m", "ETRS89 UTM; 12°E–18°E."),
    9716: _ref(9716, "IGM95 / UTM zone 34N", FAMILY_ETRS89, "projected", "metre", "UTM zone 34N", "500 000 m", "ETRS89 UTM; eastern Italy."),
    3035: _ref(3035, "ETRS89 / ETRS-LAEA", FAMILY_ETRS89, "projected", "metre", "pan-European LAEA", "4 321 000 m (x)", "Lambert Azimuthal Equal Area; pan-European statistical grid."),
    3034: _ref(3034, "ETRS89 / ETRS-LCC", FAMILY_ETRS89, "projected", "metre", "pan-European LCC", "4 000 000 m (x)", "Lambert Conformal Conic; pan-European mapping."),

    # RDN2008 family (ETRF2000 realization — the current Italian official datum)
    6706: _ref(6706, "RDN2008 2D geo", FAMILY_RDN2008, "geographic", "degree", "", "", "RDN2008 (ETRF2000) geographic; the current official Italian datum."),
    6707: _ref(6707, "RDN2008 / TM32", FAMILY_RDN2008, "projected", "metre", "Transverse Mercator zone 32 (CM 9°E)", "500 000 m", "RDN2008 UTM-style zone 32; easting ~500 000 at the central meridian."),
    6708: _ref(6708, "RDN2008 / TM33", FAMILY_RDN2008, "projected", "metre", "Transverse Mercator zone 33 (CM 15°E)", "500 000 m", "RDN2008 UTM-style zone 33; easting ~500 000 at the central meridian."),
    6709: _ref(6709, "RDN2008 / TM34", FAMILY_RDN2008, "projected", "metre", "Transverse Mercator zone 34 (CM 21°E)", "500 000 m", "RDN2008 UTM-style zone 34; eastern Italy."),
    7794: _ref(7794, "RDN2008 / Italy Zone (E-N)", FAMILY_RDN2008, "projected", "metre", "single national zone", "~7 000 000 m (zone-prefixed)", "RDN2008 single national zone; very large zone-prefixed easting (~6.7–7.1M)."),
    6876: _ref(6876, "RDN2008 / Zone 12", FAMILY_RDN2008, "projected", "metre", "zone 12", "~3 000 000 m (zone-prefixed)", "RDN2008 zone-12 system; zone-prefixed easting (~2.7–3.1M)."),
}


def ref_by_epsg(epsg: int) -> dict | None:
    """Return the static metadata for an EPSG, or ``None`` if unknown."""
    return REF_TABLE.get(epsg)


def datum_family(epsg: int) -> str:
    """Return the datum family for an EPSG, or ``""`` if unknown."""
    r = REF_TABLE.get(epsg)
    return r["datum_family"] if r else ""
