"""End-to-end tests against a real PostgreSQL + pgvector (DATABASE_URL must be set)."""

import json

import pytest
from fastapi.testclient import TestClient

from hpm import service
from hpm.embeddings import HashingEmbedder
from hpm.extract import RegexExtractor
from hpm.search import search

pytestmark = pytest.mark.db


def test_reingest_is_idempotent(Session, datasheets):
    with Session.begin() as s:
        results = service.ingest_folder(s, datasheets, HashingEmbedder(384), RegexExtractor())
    assert {r.status for r in results} == {"unchanged"}


def test_every_competitor_gets_its_expected_match(Session, datasheets):
    truth = json.loads((datasheets.parent / "ground_truth.json").read_text())
    with Session() as s:
        for comp, expected in truth["matches"].items():
            best = service.match(s, comp, top_k=1)[0]
            assert best.reference.model == expected and best.compatible, comp


def test_provenance_is_stored(Session):
    with Session() as s:
        p = service.get_product(s, "NH-P30")
        src = {x.attribute: x for x in p.sources}
    assert src["max_pressure"].raw == "Peak pressure: 5,000 psi"
    assert src["max_pressure"].page == 1


def test_hybrid_search_finds_model_code(Session):
    with Session() as s:
        hits = search(s, HashingEmbedder(384), "maximum flow of VT-D6", k=3)
    assert hits[0].filename == "VT-D6.pdf"
    assert "model_code" in hits[0].ranks


def test_keyword_search_finds_exact_standard(Session):
    with Session() as s:
        hits = search(s, HashingEmbedder(384), "ISO 4406 19/17/14", k=3, mode="keyword")
    assert all(h.manufacturer == "Vantek" for h in hits)


def test_api(Session, monkeypatch):
    from hpm import api

    monkeypatch.setattr(api, "_embedder", lambda: HashingEmbedder(384))
    client = TestClient(api.app)
    assert client.get("/health").json()["status"] == "ok"
    assert len(client.get("/products", params={"reference": True}).json()) == 12
    m = client.get("/match/VT-D6", params={"top_k": 2}).json()
    assert m[0]["reference_model"] == "OW-D6H" and m[0]["compatible"]
    assert client.get("/match/NOPE").status_code == 404
    a = client.post("/ask", json={"question": "Which cleanliness level does the VT-AX45 require?"}).json()
    assert "19/17/14" in a["answer"]
    assert a["citations"][0]["datasheet"].startswith("VT-")
