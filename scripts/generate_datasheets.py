"""Generate the demo PDF datasheets and the labelled ground truth.

    python scripts/generate_datasheets.py

Writes:
  data/datasheets/reference/*.pdf     our own portfolio (fictional brand "Ostwerk")
  data/datasheets/competitors/*.pdf   three fictional competitor brands
  data/ground_truth.json              true specs (canonical units) + expected matches

Each brand writes its datasheets in its own units and wording, like real
catalogues do, so extraction and unit normalisation have real work to do.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).parent))
from catalog import COMPETITORS, HARD_CASES, REFERENCE, REFERENCE_BRAND  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasheets"

TYPE_NAMES = {
    "axial_piston_pump": "Axial Piston Pump",
    "external_gear_pump": "External Gear Pump",
    "directional_valve": "Directional Control Valve",
}

# Valve interface names per brand. NG6 = ISO 4401-03 = CETOP 3 = D03.
SIZE_NAMES = {
    "us": {"NG6": "D03", "NG10": "D05"},
    "cetop": {"NG6": "CETOP 3 (ISO 4401-03)", "NG10": "CETOP 5 (ISO 4401-05)"},
    "ng": {"NG6": "NG6", "NG10": "NG10"},
}


def r(x: float, step: float) -> float:
    """Round to a step, the way catalogues print rounded figures."""
    return round(round(x / step) * step, 6)


def fmt(x: float) -> str:
    return f"{x:,.1f}".rstrip("0").rstrip(".") if x != int(x) else f"{int(x):,}"


# ----------------------------------------------------------------- brand styles
# Each style returns the rows of the "Technical data" table for one product.


def rows_us(p: dict) -> list[tuple[str, str]]:
    rows = []
    if p["type"] != "directional_valve":
        rows += [
            ("Displacement", f"{p['displacement'] / 16.387:.2f} in³/rev"),
            ("Peak pressure", f"{fmt(r(p['max_pressure'] * 14.5038, 50))} psi"),
            ("Continuous pressure", f"{fmt(r(p['cont_pressure'] * 14.5038, 50))} psi"),
            ("Max speed", f"{fmt(p['max_speed'])} rpm"),
            ("Circuit type", f"{p['circuit'].capitalize()} circuit"),
            ("Mounting flange", p["mounting"]),
        ]
    else:
        rows += [
            ("Valve interface", SIZE_NAMES["us"][p["size"]]),
            ("Peak pressure", f"{fmt(r(p['max_pressure'] * 14.5038, 50))} psi"),
            ("Rated flow", f"{fmt(r(p['max_flow'] / 3.78541, 0.5))} gpm"),
        ]
    rows.append(("Weight", f"{fmt(r(p['weight'] * 2.20462, 0.5))} lb"))
    return rows


def rows_mpa(p: dict) -> list[tuple[str, str]]:
    rows = []
    if p["type"] != "directional_valve":
        rows += [
            ("Vg max", f"{fmt(p['displacement'])} cm³"),
            ("p max", f"{p['max_pressure'] / 10:.1f} MPa"),
            ("p nom", f"{p['cont_pressure'] / 10:.1f} MPa"),
            ("n max", f"{fmt(p['max_speed'])} min-1"),
            ("Circuit", "closed loop" if p["circuit"] == "closed" else "open loop"),
            ("Mounting", p["mounting"]),
        ]
    else:
        rows += [
            ("Nominal size", SIZE_NAMES["ng"][p["size"]]),
            ("p max", f"{p['max_pressure'] / 10:.1f} MPa"),
            ("Q max", f"{fmt(p['max_flow'])} l/min"),
        ]
    rows.append(("Mass", f"{fmt(p['weight'])} kg"))
    return rows


def rows_bar(p: dict, long: bool) -> list[tuple[str, str]]:
    # long=True: Caldera wording, long=False: Ostwerk (reference) wording
    rows = []
    if p["type"] != "directional_valve":
        rows += [
            ("Geometric displacement" if long else "Displacement Vg", f"{fmt(p['displacement'])} cm³/rev"),
            ("Maximum pressure" if long else "Maximum pressure pmax", f"{fmt(p['max_pressure'])} bar"),
            ("Nominal pressure" if long else "Nominal pressure pnom", f"{fmt(p['cont_pressure'])} bar"),
            ("Maximum speed" if long else "Maximum speed nmax", f"{fmt(p['max_speed'])} rpm"),
            ("Circuit", f"{p['circuit']} circuit"),
            ("Mounting flange" if long else "Mounting", p["mounting"]),
        ]
    else:
        rows += [
            ("Interface" if long else "Size", SIZE_NAMES["cetop" if long else "ng"][p["size"]]),
            ("Maximum pressure" if long else "Maximum pressure pmax", f"{fmt(p['max_pressure'])} bar"),
            ("Maximum flow" if long else "Maximum flow qmax", f"{fmt(p['max_flow'])} L/min"),
        ]
    rows.append(("Weight" if long else "Weight m", f"{fmt(p['weight'])} kg"))
    return rows


BRANDS = {
    REFERENCE_BRAND: dict(
        rows=lambda p: rows_bar(p, long=False),
        fluid="ISO 4406 class 20/18/15 or better",
        temp="-20 °C to +90 °C",
        visc="10 to 1000 mm²/s",
    ),
    "Norhydra": dict(
        rows=rows_us,
        fluid="ISO 4406 18/16/13 (NAS 1638 class 7)",
        temp="-4 °F to +180 °F (-20 °C to +82 °C)",
        visc="60 to 5000 SUS",
    ),
    "Vantek": dict(rows=rows_mpa, fluid="ISO 4406 19/17/14", temp="-25 °C to +80 °C", visc="12 to 800 mm²/s"),
    "Caldera": dict(
        rows=lambda p: rows_bar(p, long=True),
        fluid="ISO 4406 20/18/15",
        temp="-15 °C to +85 °C",
        visc="15 to 1000 mm²/s",
    ),
}


def build_pdf(path: Path, brand: str, p: dict) -> None:
    style = BRANDS[brand]
    ss = getSampleStyleSheet()
    title = f"{brand} {p['model']} {TYPE_NAMES[p['type']]}"
    story = [
        Paragraph(title, ss["Title"]),
        Paragraph(f"Data sheet {p['model']} | Edition 2026-01", ss["Normal"]),
        Spacer(1, 10),
        Paragraph(
            f"The {p['model']} is {'a' if p['type'] == 'directional_valve' else 'an'} "
            f"{TYPE_NAMES[p['type']].lower()} for mobile hydraulic "
            "applications such as construction and agricultural machinery.",
            ss["Normal"],
        ),
        Spacer(1, 10),
        Paragraph("Technical data", ss["Heading2"]),
    ]
    table = Table([("Parameter", "Value"), *style["rows"](p)], colWidths=[200, 200])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story += [
        table,
        PageBreak(),
        Paragraph("Control options and features", ss["Heading2"]),
        Paragraph(p["control"], ss["Normal"]),
        Spacer(1, 10),
        Paragraph("Hydraulic fluid and operating conditions", ss["Heading2"]),
        Paragraph(
            f"Use mineral-oil based hydraulic fluids. Required cleanliness level: {style['fluid']}. "
            f"Permissible fluid temperature range: {style['temp']}. "
            f"Permissible viscosity range: {style['visc']}.",
            ss["Normal"],
        ),
        Spacer(1, 10),
        Paragraph("Installation notes", ss["Heading2"]),
        Paragraph(
            "Fill the housing with hydraulic fluid before commissioning. Make sure the suction "
            "line is free of air and that the case drain line is routed above the unit.",
            ss["Normal"],
        ),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, title=title, author=brand).build(story)


def canonical(p: dict) -> dict:
    keys = [
        "type",
        "circuit",
        "mounting",
        "size",
        "displacement",
        "max_pressure",
        "cont_pressure",
        "max_speed",
        "max_flow",
        "weight",
    ]
    return {k: p[k] for k in keys if k in p}


def main() -> None:
    truth = {"products": {}, "matches": {}, "hard_cases": HARD_CASES}
    (OUT / "reference").mkdir(parents=True, exist_ok=True)
    (OUT / "competitors").mkdir(parents=True, exist_ok=True)
    for p in REFERENCE:
        build_pdf(OUT / "reference" / f"{p['model']}.pdf", REFERENCE_BRAND, p)
        truth["products"][p["model"]] = {"brand": REFERENCE_BRAND, **canonical(p)}
    for brand, items in COMPETITORS.items():
        for p in items:
            build_pdf(OUT / "competitors" / f"{p['model']}.pdf", brand, p)
            truth["products"][p["model"]] = {"brand": brand, **canonical(p)}
            truth["matches"][p["model"]] = p["expected"]
    (ROOT / "data" / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    n = len(truth["products"])
    print(f"Wrote {n} datasheets ({len(REFERENCE)} reference, {n - len(REFERENCE)} competitor)")


if __name__ == "__main__":
    main()
