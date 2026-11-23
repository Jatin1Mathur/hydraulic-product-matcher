"""REST API.  Run:  uvicorn hpm.api:app --reload   then open http://localhost:8000/docs"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from hpm import __version__, service
from hpm.config import settings
from hpm.db import make_engine, make_session_factory
from hpm.embeddings import Embedder, make_embedder
from hpm.llm import OllamaClient
from hpm.rag import answer

app = FastAPI(
    title="Hydraulic Product Matcher",
    version=__version__,
    description="Competitor datasheets -> structured database -> explainable product matches",
)


@lru_cache
def _session_factory():
    return make_session_factory(make_engine())


@lru_cache
def _embedder() -> Embedder:
    return make_embedder(settings)


def get_session() -> Iterator[Session]:
    with _session_factory()() as s:
        yield s


# ---------------------------------------------------------------- response models
class SourceOut(BaseModel):
    attribute: str
    raw: str
    page: int | None
    method: str
    verified: bool


class ProductOut(BaseModel):
    model: str
    manufacturer: str
    is_reference: bool
    component_type: str
    circuit: str | None
    mounting: str | None
    nominal_size: str | None
    displacement_cm3_rev: float | None
    max_pressure_bar: float | None
    cont_pressure_bar: float | None
    max_speed_rpm: float | None
    max_flow_l_min: float | None
    weight_kg: float | None
    control_text: str | None
    datasheet: str | None
    sources: list[SourceOut] = []


class CriterionOut(BaseModel):
    name: str
    passed: bool | None
    hard: bool
    score: float
    detail: str


class MatchOut(BaseModel):
    reference_model: str
    compatible: bool
    total: float
    spec_score: float
    semantic_score: float
    criteria: list[CriterionOut]


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    manufacturer: str | None = None


class PassageOut(BaseModel):
    datasheet: str
    page: int
    text: str


class AskOut(BaseModel):
    answer: str
    generated: bool
    citations: list[PassageOut]


def _product_out(p, with_sources: bool = False) -> ProductOut:
    return ProductOut(
        model=p.model,
        manufacturer=p.manufacturer.name,
        is_reference=p.manufacturer.is_reference,
        component_type=p.component_type,
        circuit=p.circuit,
        mounting=p.mounting,
        nominal_size=p.nominal_size,
        displacement_cm3_rev=p.displacement,
        max_pressure_bar=p.max_pressure,
        cont_pressure_bar=p.cont_pressure,
        max_speed_rpm=p.max_speed,
        max_flow_l_min=p.max_flow,
        weight_kg=p.weight,
        control_text=p.control_text,
        datasheet=p.document.filename if p.document else None,
        sources=[
            SourceOut(attribute=s.attribute, raw=s.raw, page=s.page, method=s.method, verified=s.verified)
            for s in p.sources
        ]
        if with_sources
        else [],
    )


# ---------------------------------------------------------------- endpoints
@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    return {"status": "ok", "embedder": settings.embedder, "extractor": settings.extractor}


@app.get("/products", response_model=list[ProductOut])
def products(reference: bool | None = None, component_type: str | None = None, session: Session = Depends(get_session)):
    return [_product_out(p) for p in service.list_products(session, reference, component_type)]


@app.get("/products/{model}", response_model=ProductOut)
def product(model: str, session: Session = Depends(get_session)):
    p = service.get_product(session, model)
    if p is None:
        raise HTTPException(404, f"Unknown product {model}")
    return _product_out(p, with_sources=True)


@app.get("/match/{model}", response_model=list[MatchOut])
def match(
    model: str,
    top_k: int = Query(3, ge=1, le=20),
    mode: str = Query("rules+semantic", pattern="^(naive|rules|rules\\+semantic|semantic)$"),
    session: Session = Depends(get_session),
):
    try:
        results = service.match(session, model, mode=mode, top_k=top_k)
    except KeyError:
        raise HTTPException(404, f"Unknown product {model}") from None
    return [
        MatchOut(
            reference_model=m.reference.model,
            compatible=m.compatible,
            total=m.total,
            spec_score=m.spec_score,
            semantic_score=m.semantic_score,
            criteria=[
                CriterionOut(name=c.name, passed=c.passed, hard=c.hard, score=round(c.score, 3), detail=c.detail)
                for c in m.criteria
            ],
        )
        for m in results
    ]


@app.post("/ask", response_model=AskOut)
def ask(body: AskIn, session: Session = Depends(get_session)):
    llm = OllamaClient(settings.ollama_url, settings.llm_model) if settings.rag_llm else None
    a = answer(session, _embedder(), body.question, llm=llm, manufacturer=body.manufacturer)
    return AskOut(
        answer=a.text,
        generated=a.generated,
        citations=[PassageOut(datasheet=h.filename, page=h.page, text=h.text) for h in a.citations],
    )
