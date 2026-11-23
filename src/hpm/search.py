"""Hybrid retrieval over datasheet chunks.

Two retrievers, each good at something different:
  vector   pgvector cosine distance; finds passages with the same *meaning*
  keyword  PostgreSQL full-text search (ts_rank_cd); finds exact terms like "ISO 4406" or "NG10"
Their rankings are merged with Reciprocal Rank Fusion (RRF): score = sum 1 / (60 + rank).
RRF only uses ranks, so the two very different score scales never have to be calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from hpm.db import Chunk, Document, Manufacturer, Product
from hpm.embeddings import Embedder
from hpm.extract import MODEL_CODE

RRF_K = 60


@dataclass
class Hit:
    chunk_id: int
    filename: str
    manufacturer: str
    page: int
    text: str
    score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)


def _vector(session: Session, embedder: Embedder, query: str, n: int, manufacturer: str | None) -> list[int]:
    q = embedder.embed_query(query)
    stmt = select(Chunk.id).join(Document).join(Manufacturer)
    if manufacturer:
        stmt = stmt.where(Manufacturer.name == manufacturer)
    stmt = stmt.order_by(Chunk.embedding.cosine_distance(q)).limit(n)
    return list(session.scalars(stmt))


_KEYWORD_SQL = text("""
    WITH q AS (
        -- OR the query terms together so a natural-language question still matches
        SELECT to_tsquery('english', replace(plainto_tsquery('english', :query)::text, '&', '|')) AS tsq
    )
    SELECT c.id
    FROM chunks c JOIN documents d ON d.id = c.document_id
                  JOIN manufacturers m ON m.id = d.manufacturer_id, q
    WHERE c.tsv @@ q.tsq AND (CAST(:mfr AS text) IS NULL OR m.name = :mfr)
    ORDER BY ts_rank_cd(c.tsv, q.tsq) DESC
    LIMIT :n
""")


def _keyword(session: Session, query: str, n: int, manufacturer: str | None) -> list[int]:
    return list(session.scalars(_KEYWORD_SQL, {"query": query, "n": n, "mfr": manufacturer}))


def _model_codes(session: Session, query: str, n: int) -> list[int]:
    """Chunks of datasheets whose product code is named in the query (e.g. "VT-D6").

    A cheap entity lookup: identifiers are exactly where embeddings are weakest,
    and an engineer who types a code wants that datasheet.
    """
    codes = {c.upper() for c in MODEL_CODE.findall(query.upper())}
    if not codes:
        return []
    stmt = (
        select(Chunk.id)
        .join(Document)
        .join(Product, Product.document_id == Document.id)
        .where(Product.model.in_(codes))
        .order_by(Chunk.page, Chunk.chunk_index)
        .limit(n)
    )
    return list(session.scalars(stmt))


def rrf(rankings: dict[str, list[int]], k: int = RRF_K) -> list[tuple[int, float, dict[str, int]]]:
    scores: dict[int, float] = {}
    ranks: dict[int, dict[str, int]] = {}
    for name, ids in rankings.items():
        for rank, cid in enumerate(ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            ranks.setdefault(cid, {})[name] = rank
    return sorted(((cid, s, ranks[cid]) for cid, s in scores.items()), key=lambda t: -t[1])


def search(
    session: Session,
    embedder: Embedder,
    query: str,
    k: int = 5,
    mode: str = "hybrid",
    manufacturer: str | None = None,
    n_candidates: int = 20,
) -> list[Hit]:
    rankings: dict[str, list[int]] = {}
    if mode in ("hybrid", "vector"):
        rankings["vector"] = _vector(session, embedder, query, n_candidates, manufacturer)
    if mode in ("hybrid", "keyword"):
        rankings["keyword"] = _keyword(session, query, n_candidates, manufacturer)
    if mode == "hybrid":
        rankings["model_code"] = _model_codes(session, query, n_candidates)
    fused = rrf(rankings)[:k]
    if not fused:
        return []
    rows = {c.id: c for c in session.scalars(select(Chunk).where(Chunk.id.in_([f[0] for f in fused])))}
    hits = []
    for cid, score, rk in fused:
        c = rows[cid]
        hits.append(Hit(cid, c.document.filename, c.document.manufacturer.name, c.page, c.text, score, rk))
    return hits
