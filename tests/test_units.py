import pytest

from hpm import units
from hpm.schemas import ComponentType, ExtractedSpec, RawValue, normalise


@pytest.mark.parametrize(
    ("value", "unit", "qty", "expected"),
    [
        (5000, "psi", "pressure", 344.74),
        (31.5, "MPa", "pressure", 315.0),
        (350, "bar", "pressure", 350.0),
        (1.83, "in³/rev", "displacement", 29.99),
        (46, "cm³", "displacement", 46.0),
        (21, "gpm", "flow", 79.49),
        (100, "l/min", "flow", 100.0),
        (2700, "min-1", "speed", 2700.0),
        (33, "lb", "mass", 14.97),
    ],
)
def test_to_canonical(value, unit, qty, expected):
    assert units.to_canonical(value, unit, qty) == pytest.approx(expected, rel=1e-3)


def test_unknown_unit_raises_instead_of_guessing():
    with pytest.raises(units.UnitError):
        units.to_canonical(10, "atm", "pressure")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5,000 psi", (5000.0, "psi")),
        ("1.83 in³/rev", (1.83, "in³/rev")),
        ("NG6", None),
    ],
)
def test_parse_quantity(text, expected):
    assert units.parse_quantity(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("NG6", "NG6"),
        ("NG 10", "NG10"),
        ("D03", "NG6"),
        ("D05", "NG10"),
        ("CETOP 3 (ISO 4401-03)", "NG6"),
        ("CETOP 5", "NG10"),
        ("ISO 4401-05", "NG10"),
        ("size X", None),
    ],
)
def test_valve_sizes_are_equivalent(text, expected):
    assert units.normalise_valve_size(text) == expected


def test_normalise_drops_implausible_values():
    raw = ExtractedSpec(
        manufacturer="X",
        model="X-1",
        component_type=ComponentType.AXIAL_PISTON_PUMP,
        displacement=RawValue(value=45, unit="cm3"),
        max_pressure=RawValue(value=35000, unit="bar"),
    )  # typo in a datasheet
    spec, warnings = normalise(raw)
    assert spec.displacement == 45
    assert spec.max_pressure is None
    assert any("plausible" in w for w in warnings)
