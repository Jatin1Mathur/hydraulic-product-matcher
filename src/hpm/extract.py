"""Turn datasheet pages into an ExtractedSpec.

Two extractors:

RegexExtractor  reads the "Technical data" table with a list of label synonyms.
                Fast, free, deterministic, but only knows labels it was told about.
LLMExtractor    asks a local LLM to fill the ExtractedSpec JSON schema. Handles
                wording it has never seen. Every number it returns is checked
                against the source text (anti-hallucination), and gaps are filled
                by the regex extractor.

Both record provenance: which page each value came from and which method found it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from hpm.llm import LLMError, OllamaClient
from hpm.pdf import Page
from hpm.schemas import ComponentType, ExtractedSpec, RawValue
from hpm.units import parse_quantity

NUMERIC_FIELDS = ["displacement", "max_pressure", "cont_pressure", "max_speed", "max_flow", "weight"]
TEXT_FIELDS = ["circuit", "mounting", "nominal_size"]

# Label synonyms per field, checked in this order (first match wins).
LABELS: list[tuple[str, re.Pattern]] = [
    ("nominal_size", re.compile(r"interface|nominal size|^size\b", re.I)),
    ("cont_pressure", re.compile(r"continuous pressure|nominal pressure|rated pressure|\bp ?nom\b", re.I)),
    ("max_pressure", re.compile(r"peak pressure|max(imum|\.)? pressure|\bp ?max\b", re.I)),
    ("max_speed", re.compile(r"max(imum|\.)? speed|\bn ?max\b", re.I)),
    ("max_flow", re.compile(r"rated flow|max(imum|\.)? flow|\bq ?max\b", re.I)),
    ("displacement", re.compile(r"displacement|\bvg\b", re.I)),
    ("weight", re.compile(r"weight|mass", re.I)),
    ("circuit", re.compile(r"circuit", re.I)),
    ("mounting", re.compile(r"mounting", re.I)),
]

TYPE_KEYWORDS = [
    (ComponentType.AXIAL_PISTON_PUMP, re.compile(r"axial piston pump", re.I)),
    (ComponentType.EXTERNAL_GEAR_PUMP, re.compile(r"gear pump", re.I)),
    (ComponentType.DIRECTIONAL_VALVE, re.compile(r"directional (control |spool )?valve", re.I)),
]

MODEL_CODE = re.compile(r"\b[A-Z]{2,4}-[A-Z0-9]+\b")


@dataclass
class Provenance:
    page: int | None
    raw: str
    method: str  # "regex" | "llm"
    verified: bool = True  # number found verbatim in the source text


@dataclass
class Extraction:
    spec: ExtractedSpec
    provenance: dict[str, Provenance] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _label_field(label: str) -> str | None:
    for name, pattern in LABELS:
        if pattern.search(label):
            return name
    return None


class RegexExtractor:
    name = "regex"

    def extract(self, pages: list[Page]) -> Extraction:
        data: dict = {}
        prov: dict[str, Provenance] = {}

        title = pages[0].text.splitlines()[0] if pages and pages[0].text else ""
        data["manufacturer"] = title.split()[0] if title else None
        m = MODEL_CODE.search(title)
        data["model"] = m.group(0) if m else None
        for ctype, pattern in TYPE_KEYWORDS:
            if pattern.search(title):
                data["component_type"] = ctype
                break

        for page in pages:
            rows = [row for table in page.tables for row in table if row and len(row) >= 2]
            for label, value, *_ in rows:
                if not label or not value:
                    continue
                name = _label_field(label)
                if name is None or name in data:
                    continue
                if name in NUMERIC_FIELDS:
                    q = parse_quantity(value)
                    if q is None:
                        continue
                    data[name] = RawValue(value=q[0], unit=q[1])
                else:
                    data[name] = value
                prov[name] = Provenance(page.number, f"{label}: {value}", self.name)

            control = _section_after(page.text, "control option")
            if control and "control_text" not in data:
                data["control_text"] = control
                prov["control_text"] = Provenance(page.number, control, self.name)

        return Extraction(ExtractedSpec(**data), prov)


def _section_after(text: str, keyword: str) -> str | None:
    """Text of the first paragraph after a heading line containing `keyword`."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if keyword in line.lower() and len(line) < 60:
            body = []
            for nxt in lines[i + 1 :]:
                if body and (len(nxt) < 60 and not nxt.rstrip().endswith((".", ","))):
                    break  # next heading
                body.append(nxt.strip())
                if nxt.rstrip().endswith("."):
                    break
            return " ".join(body) or None
    return None


def _number_in_text(value: float, text: str) -> bool:
    """True if `value` appears in `text` (thousands separators ignored)."""
    plain = text.replace(",", "")
    candidates = {f"{value:g}", f"{value:.1f}", f"{value:.2f}"}
    if value == int(value):
        candidates.add(str(int(value)))
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", plain) for c in candidates)


SYSTEM_PROMPT = """You extract technical data from hydraulic component datasheets.
Return JSON that matches the given schema.
Rules:
- Copy every number and unit exactly as printed. Do NOT convert units.
- Use null for anything the datasheet does not state. Never guess.
- component_type is one of: axial_piston_pump, external_gear_pump, directional_valve.
"""


class LLMExtractor:
    name = "llm"

    def __init__(self, client: OllamaClient, fallback: RegexExtractor | None = None, max_chars: int = 8000):
        self.client = client
        self.fallback = fallback or RegexExtractor()
        self.max_chars = max_chars

    def extract(self, pages: list[Page]) -> Extraction:
        source = "\n\n".join(f"[page {p.number}]\n{p.text}" for p in pages)[: self.max_chars]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"DATASHEET:\n{source}"},
        ]
        schema = ExtractedSpec.model_json_schema()
        warnings: list[str] = []
        spec: ExtractedSpec | None = None
        for attempt in range(2):  # one retry with the validation error fed back
            try:
                raw = self.client.chat(messages, schema=schema)
                spec = ExtractedSpec.model_validate(json.loads(raw))
                break
            except (json.JSONDecodeError, ValidationError) as exc:
                warnings.append(f"LLM output invalid (attempt {attempt + 1}): {str(exc)[:200]}")
                messages.append({"role": "user", "content": f"Your JSON was invalid: {exc}. Try again."})
            except LLMError as exc:
                warnings.append(str(exc))
                break

        base = self.fallback.extract(pages)
        if spec is None:
            base.warnings += warnings + ["fell back to regex extraction"]
            return base

        data = spec.model_dump()
        prov: dict[str, Provenance] = {}
        for name in NUMERIC_FIELDS:
            rv = getattr(spec, name)
            if rv is None:
                continue
            page = next((p.number for p in pages if _number_in_text(rv.value, p.text)), None)
            if page is None:
                # The number is not in the document: treat as hallucination and drop it.
                warnings.append(f"{name}: LLM value {rv.value} {rv.unit} not found in source, dropped")
                data[name] = None
                continue
            prov[name] = Provenance(page, f"{rv.value:g} {rv.unit}", self.name)
        for name in ["manufacturer", "model", "component_type", "control_text", *TEXT_FIELDS]:
            if data.get(name) is not None:
                prov[name] = Provenance(None, str(data[name]), self.name, verified=False)

        # Fill gaps from the deterministic extractor
        for name, value in base.spec.model_dump().items():
            if data.get(name) is None and value is not None:
                data[name] = value
                prov[name] = base.provenance.get(name, Provenance(None, str(value), "regex"))
        return Extraction(ExtractedSpec.model_validate(data), prov, warnings)
