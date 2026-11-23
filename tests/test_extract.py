import json

import httpx
import pytest

from hpm.extract import LLMExtractor, RegexExtractor, _number_in_text
from hpm.llm import OllamaClient
from hpm.pdf import Page, chunk_pages, read_pdf
from hpm.schemas import ComponentType, normalise


def test_regex_extracts_us_units(datasheets):
    e = RegexExtractor().extract(read_pdf(datasheets / "competitors" / "NH-P30.pdf"))
    spec, warnings = normalise(e.spec)
    assert (spec.manufacturer, spec.model, spec.component_type) == (
        "Norhydra",
        "NH-P30",
        ComponentType.AXIAL_PISTON_PUMP,
    )
    assert spec.displacement == pytest.approx(30, rel=0.01)
    assert spec.max_pressure == pytest.approx(345, rel=0.01)
    assert spec.circuit == "open" and spec.mounting == "SAE B"
    assert "load sense" in spec.control_text
    assert e.provenance["max_pressure"].page == 1
    assert warnings == []


def test_regex_extracts_mpa_valve(datasheets):
    spec, _ = normalise(RegexExtractor().extract(read_pdf(datasheets / "competitors" / "VT-D6.pdf")).spec)
    assert spec.component_type == ComponentType.DIRECTIONAL_VALVE
    assert (spec.nominal_size, spec.max_pressure, spec.max_flow) == ("NG6", 315.0, 100.0)


def test_chunks_carry_title(datasheets):
    pages = read_pdf(datasheets / "competitors" / "VT-D6.pdf")
    chunks = chunk_pages(pages, "Vantek VT-D6 Directional Control Valve")
    assert all(c.text.startswith("Vantek VT-D6") for c in chunks)
    assert {c.page for c in chunks} == {1, 2}


def test_number_in_text_ignores_thousands_separator():
    assert _number_in_text(5000, "Peak pressure 5,000 psi")
    assert _number_in_text(31.5, "p max 31.5 MPa")
    assert not _number_in_text(500, "Peak pressure 5,000 psi")


def _fake_ollama(reply: dict) -> OllamaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["format"]["title"] == "ExtractedSpec"  # JSON schema is sent
        return httpx.Response(200, json={"message": {"content": json.dumps(reply)}})

    return OllamaClient("http://ollama", "test", transport=httpx.MockTransport(handler))


PAGES = [Page(1, "Acme AC-1 Axial Piston Pump\nDisplacement 45 cm³/rev\nPeak pressure 5,000 psi", [])]


def test_llm_extractor_keeps_verified_values():
    client = _fake_ollama(
        {
            "manufacturer": "Acme",
            "model": "AC-1",
            "component_type": "axial_piston_pump",
            "displacement": {"value": 45, "unit": "cm³/rev"},
            "max_pressure": {"value": 5000, "unit": "psi"},
        }
    )
    e = LLMExtractor(client).extract(PAGES)
    assert e.spec.max_pressure.value == 5000
    assert e.provenance["max_pressure"].method == "llm"
    assert e.provenance["max_pressure"].page == 1


def test_llm_extractor_drops_hallucinated_numbers():
    client = _fake_ollama(
        {
            "manufacturer": "Acme",
            "model": "AC-1",
            "component_type": "axial_piston_pump",
            "displacement": {"value": 45, "unit": "cm³/rev"},
            "max_speed": {"value": 3000, "unit": "rpm"},
        }
    )  # not in the datasheet
    e = LLMExtractor(client).extract(PAGES)
    assert e.spec.max_speed is None
    assert any("not found in source" in w for w in e.warnings)


def test_llm_extractor_falls_back_to_regex_when_ollama_is_down():
    def down(request):
        raise httpx.ConnectError("refused")

    client = OllamaClient("http://ollama", "test", transport=httpx.MockTransport(down))
    e = LLMExtractor(client).extract(PAGES)
    assert "fell back to regex extraction" in e.warnings
