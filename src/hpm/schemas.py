"""Data contracts.

ExtractedSpec  what an extractor reads from a datasheet, values *as written* (value + unit).
ProductSpec    the normalised record stored in the database, canonical units only.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from hpm import units


class ComponentType(StrEnum):
    AXIAL_PISTON_PUMP = "axial_piston_pump"
    EXTERNAL_GEAR_PUMP = "external_gear_pump"
    DIRECTIONAL_VALVE = "directional_valve"

    @property
    def is_pump(self) -> bool:
        return self is not ComponentType.DIRECTIONAL_VALVE


class RawValue(BaseModel):
    value: float = Field(description="The number exactly as printed, without thousands separators")
    unit: str = Field(description="The unit exactly as printed, e.g. psi, MPa, bar, in³/rev, gpm, lb")


class ExtractedSpec(BaseModel):
    """Schema the LLM must fill. Leave a field null if the datasheet does not state it."""

    manufacturer: str | None = None
    model: str | None = Field(None, description="Model or type code, e.g. NH-P30")
    component_type: ComponentType | None = None
    circuit: str | None = Field(None, description="open or closed circuit, as written")
    mounting: str | None = Field(None, description="Mounting flange, e.g. SAE B")
    nominal_size: str | None = Field(None, description="Valve size/interface, e.g. NG6, D03, CETOP 5")
    displacement: RawValue | None = None
    max_pressure: RawValue | None = Field(None, description="Peak / maximum pressure")
    cont_pressure: RawValue | None = Field(None, description="Continuous / nominal / rated pressure")
    max_speed: RawValue | None = None
    max_flow: RawValue | None = None
    weight: RawValue | None = Field(None, description="Weight or mass")
    control_text: str | None = Field(None, description="Control options and features, one or two sentences")


QUANTITY_OF = {
    "displacement": "displacement",
    "max_pressure": "pressure",
    "cont_pressure": "pressure",
    "max_speed": "speed",
    "max_flow": "flow",
    "weight": "mass",
}

# Plausibility limits for mobile hydraulics, in canonical units. A value outside is flagged.
PLAUSIBLE = {
    "displacement": (0.5, 1000),
    "max_pressure": (20, 700),
    "cont_pressure": (20, 700),
    "max_speed": (100, 10000),
    "max_flow": (1, 2000),
    "weight": (0.1, 1000),
}


class ProductSpec(BaseModel):
    manufacturer: str
    model: str
    component_type: ComponentType
    circuit: str | None = None
    mounting: str | None = None
    nominal_size: str | None = None
    displacement: float | None = None  # cm3/rev
    max_pressure: float | None = None  # bar
    cont_pressure: float | None = None  # bar
    max_speed: float | None = None  # rpm
    max_flow: float | None = None  # L/min
    weight: float | None = None  # kg
    control_text: str | None = None

    def profile_text(self) -> str:
        """Short text used for the product embedding (semantic similarity of features)."""
        parts = [self.component_type.value.replace("_", " ")]
        if self.circuit:
            parts.append(f"{self.circuit} circuit")
        if self.nominal_size:
            parts.append(f"size {self.nominal_size}")
        if self.control_text:
            parts.append(self.control_text)
        return ". ".join(parts)


def normalise(raw: ExtractedSpec) -> tuple[ProductSpec, list[str]]:
    """Convert an ExtractedSpec to canonical units. Returns the spec and a list of warnings."""
    if not raw.manufacturer or not raw.model or not raw.component_type:
        raise ValueError("manufacturer, model and component_type are required")
    warnings: list[str] = []
    data: dict = {
        "manufacturer": raw.manufacturer.strip(),
        "model": raw.model.strip(),
        "component_type": raw.component_type,
        "circuit": units.normalise_circuit(raw.circuit),
        "mounting": units.normalise_mounting(raw.mounting),
        "nominal_size": units.normalise_valve_size(raw.nominal_size),
        "control_text": raw.control_text,
    }
    for field, quantity in QUANTITY_OF.items():
        rv: RawValue | None = getattr(raw, field)
        if rv is None:
            continue
        try:
            value = round(units.to_canonical(rv.value, rv.unit, quantity), 2)
        except units.UnitError as exc:
            warnings.append(f"{field}: {exc}")
            continue
        lo, hi = PLAUSIBLE[field]
        if not lo <= value <= hi:
            warnings.append(f"{field}: {value} outside plausible range {lo}-{hi}, dropped")
            continue
        data[field] = value
    if raw.nominal_size and not data["nominal_size"]:
        warnings.append(f"nominal_size: unknown interface {raw.nominal_size!r}")
    return ProductSpec(**data), warnings
