"""Unit normalisation.

Rule of the project: the LLM (or regex) only copies values *as written* in the
datasheet, e.g. (5000, "psi"). All arithmetic happens here, in tested code,
because language models are unreliable at unit conversion.
"""

from __future__ import annotations

import re

# Factor to convert one unit into the canonical unit of its quantity.
CANONICAL = {
    "pressure": "bar",
    "displacement": "cm3/rev",
    "speed": "rpm",
    "flow": "L/min",
    "mass": "kg",
}

FACTORS: dict[str, dict[str, float]] = {
    "pressure": {"bar": 1.0, "psi": 1 / 14.5038, "mpa": 10.0, "kpa": 0.01},
    "displacement": {
        "cm3/rev": 1.0,
        "cm3": 1.0,
        "cc/rev": 1.0,
        "cc": 1.0,
        "ccm": 1.0,
        "in3/rev": 16.387064,
        "in3": 16.387064,
        "cir": 16.387064,
    },
    "speed": {"rpm": 1.0, "min-1": 1.0, "1/min": 1.0, "r/min": 1.0},
    "flow": {"l/min": 1.0, "lpm": 1.0, "gpm": 3.785412, "usgpm": 3.785412},
    "mass": {"kg": 1.0, "lb": 0.45359237, "lbs": 0.45359237},
}


class UnitError(ValueError):
    """Raised for a unit the converter does not know. Better to fail than guess."""


def clean_unit(unit: str) -> str:
    u = unit.strip().lower()
    u = u.replace("³", "3").replace("⁻¹", "-1").replace("−", "-").replace(" ", "")
    u = u.replace("u.s.gpm", "gpm").replace("usgpm", "gpm")
    return u


def to_canonical(value: float, unit: str, quantity: str) -> float:
    table = FACTORS[quantity]
    u = clean_unit(unit)
    if u not in table:
        raise UnitError(f"unknown {quantity} unit {unit!r}")
    return value * table[u]


_NUMBER = re.compile(r"^\s*([-+]?\d[\d,]*(?:\.\d+)?)\s*(.*?)\s*$")


def parse_quantity(text: str) -> tuple[float, str] | None:
    """'5,000 psi' -> (5000.0, 'psi'). Returns None if the text does not start with a number."""
    m = _NUMBER.match(text)
    if not m:
        return None
    return float(m.group(1).replace(",", "")), m.group(2)


# Valve interface sizes: ISO 4401-03 = NG6 = CETOP 3 = D03, ISO 4401-05 = NG10 = CETOP 5 = D05
_SIZE = re.compile(r"NG\s*(6|10)\b|\bD0?([35])\b|CETOP\s*0?([35])\b|4401-0([35])", re.IGNORECASE)
_ISO_TO_NG = {"3": "NG6", "5": "NG10"}


def normalise_valve_size(text: str | None) -> str | None:
    if not text:
        return None
    m = _SIZE.search(text)
    if not m:
        return None
    if m.group(1):
        return f"NG{m.group(1)}"
    iso = m.group(2) or m.group(3) or m.group(4)
    return _ISO_TO_NG[iso]


def normalise_circuit(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    if "closed" in t:
        return "closed"
    if "open" in t:
        return "open"
    return None


def normalise_mounting(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"SAE\s*-?\s*([A-F])\b", text, re.IGNORECASE)
    return f"SAE {m.group(1).upper()}" if m else text.strip()
