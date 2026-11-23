"""Application services: ingest datasheets, list products, match, ask."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from hpm import matching
from hpm.config import Settings
from hpm.db import Chunk, Document, Manufacturer, Product, SpecSource
from hpm.embeddings import Embedder, cosine
from hpm.extract import LLMExtractor, RegexExtractor
from hpm.llm import OllamaClient
from hpm.pdf import chunk_pages, read_pdf
from hpm.schemas import ComponentType, ProductSpec, normalise

log = logging.getLogger(__name__)

SPEC_FIELDS = [
    "manufacturer",
    "model",
    "component_type",
    "circuit",
    "mounting",
    "nominal_size",
    "displacement",
    "max_pressure",
    "cont_pressure",
    "max_speed",
    "max_flow",
    "weight",
    "control_text",
]


def make_extractor(s: Settings) -> RegexExtractor | LLMExtractor:
    if s.extractor == "llm":
        return LLMExtractor(OllamaClient(s.ollama_url, s.llm_model))
    return RegexExtractor()


@dataclass
class IngestResult:
    filename: str
    model: str | None
    status: str  # "ingested" | "unchanged" | "failed"
    warnings: list[str]


def _manufacturer(session: Session, name: str, is_reference: bool) -> Manufacturer:
    m = session.scalar(select(Manufacturer).where(Manufacturer.name == name))
    if m is None:
        m = Manufacturer(name=name, is_reference=is_reference)
        session.add(m)
        session.flush()
    return m


def ingest_pdf(session: Session, path: Path, embedder: Embedder, extractor, is_reference: bool) -> IngestResult:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if session.scalar(select(Document.id).where(Document.sha256 == digest)):
        return IngestResult(path.name, None, "unchanged", [])

    pages = read_pdf(path)
    extraction = extractor.extract(pages)
    try:
        spec, warnings = normalise(extraction.spec)
    except ValueError as exc:
        return IngestResult(path.name, None, "failed", [str(exc), *extraction.warnings])
    warnings = extraction.warnings + warnings

    mfr = _manufacturer(session, spec.manufacturer, is_reference)
    # Re-ingesting a changed datasheet replaces the old version
    old = session.scalar(select(Product).where(Product.manufacturer_id == mfr.id, Product.model == spec.model))
    if old is not None:
        old_doc = old.document_id
        session.delete(old)
        session.flush()
        if old_doc:
            session.execute(delete(Document).where(Document.id == old_doc))

    doc = Document(manufacturer=mfr, filename=path.name, sha256=digest, n_pages=len(pages))
    title = pages[0].text.splitlines()[0] if pages and pages[0].text else path.stem
    chunks = chunk_pages(pages, title)
    vectors = embedder.embed_documents([c.text for c in chunks])
    doc.chunks = [
        Chunk(page=c.page, chunk_index=c.index, text=c.text, embedding=v) for c, v in zip(chunks, vectors, strict=True)
    ]
    session.add(doc)
    session.flush()

    values = spec.model_dump(exclude={"manufacturer"})
    product = Product(
        manufacturer=mfr,
        document=doc,
        embedding=embedder.embed_documents([spec.profile_text()])[0],
        **{k: (v.value if isinstance(v, ComponentType) else v) for k, v in values.items()},
    )
    product.sources = [
        SpecSource(attribute=k, raw=p.raw, page=p.page, method=p.method, verified=p.verified)
        for k, p in extraction.provenance.items()
    ]
    session.add(product)
    session.flush()
    return IngestResult(path.name, spec.model, "ingested", warnings)


def ingest_folder(session: Session, folder: Path, embedder: Embedder, extractor) -> list[IngestResult]:
    """PDFs under a folder named 'reference' are our own portfolio; all others are competitors."""
    results = []
    for path in sorted(folder.rglob("*.pdf")):
        is_ref = "reference" in path.parts
        results.append(ingest_pdf(session, path, embedder, extractor, is_ref))
    return results


def to_spec(p: Product) -> ProductSpec:
    return ProductSpec(
        manufacturer=p.manufacturer.name,
        model=p.model,
        component_type=ComponentType(p.component_type),
        **{k: getattr(p, k) for k in SPEC_FIELDS[3:]},
    )


# Load related rows up front so objects stay usable after the session closes (UI, API)
_EAGER = (joinedload(Product.manufacturer), joinedload(Product.document))


def list_products(session: Session, reference: bool | None = None, component_type: str | None = None) -> list[Product]:
    stmt = select(Product).join(Manufacturer).options(*_EAGER).order_by(Manufacturer.name, Product.model)
    if reference is not None:
        stmt = stmt.where(Manufacturer.is_reference == reference)
    if component_type:
        stmt = stmt.where(Product.component_type == component_type)
    return list(session.scalars(stmt))


def get_product(session: Session, model: str) -> Product | None:
    return session.scalar(select(Product).options(*_EAGER, selectinload(Product.sources)).where(Product.model == model))


def match(session: Session, model: str, mode: str = "rules+semantic", top_k: int = 5) -> list[matching.MatchResult]:
    comp = get_product(session, model)
    if comp is None:
        raise KeyError(model)
    refs = list_products(session, reference=True)
    sem = {r.model: max(0.0, cosine(np.asarray(comp.embedding), np.asarray(r.embedding))) for r in refs}
    return matching.rank(to_spec(comp), [to_spec(r) for r in refs], sem, mode=mode)[:top_k]
