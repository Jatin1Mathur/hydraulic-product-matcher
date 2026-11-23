"""Retrieval-augmented question answering over the datasheets, with page citations.

retrieve (hybrid search) -> build a numbered context -> LLM answers ONLY from it, citing [n]
Without an LLM (offline mode) the answer is the best matching passages, still cited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from hpm.embeddings import Embedder
from hpm.llm import OllamaClient
from hpm.search import Hit, search

SYSTEM = """You answer questions about hydraulic component datasheets.
Use ONLY the numbered context passages. After each fact, cite its passage like [2].
If the context does not contain the answer, reply exactly: "Not found in the datasheets."
Keep units exactly as written in the context."""


@dataclass
class Answer:
    text: str
    citations: list[Hit] = field(default_factory=list)
    passages: list[Hit] = field(default_factory=list)
    generated: bool = False


def _context(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{i}] ({h.filename}, page {h.page})\n{h.text}" for i, h in enumerate(hits, start=1))


def answer(
    session: Session,
    embedder: Embedder,
    question: str,
    llm: OllamaClient | None = None,
    k: int = 4,
    manufacturer: str | None = None,
) -> Answer:
    hits = search(session, embedder, question, k=k, manufacturer=manufacturer)
    if not hits:
        return Answer("Not found in the datasheets.")
    if llm is None:
        best = hits[0]
        return Answer(
            f"Most relevant passage ({best.filename}, page {best.page}):\n{best.text}", citations=[best], passages=hits
        )
    reply = llm.chat(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"CONTEXT:\n{_context(hits)}\n\nQUESTION: {question}"},
        ]
    )
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", reply) if 1 <= int(n) <= len(hits)})
    return Answer(reply.strip(), citations=[hits[n - 1] for n in cited], passages=hits, generated=True)
