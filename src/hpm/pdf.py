"""PDF reading and chunking."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


@dataclass
class Page:
    number: int  # 1-based
    text: str
    tables: list[list[list[str | None]]] = field(default_factory=list)


@dataclass
class Chunk:
    page: int
    index: int
    text: str


def read_pdf(path: str | Path) -> list[Page]:
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            pages.append(Page(number=i, text=p.extract_text() or "", tables=p.extract_tables() or []))
    return pages


def chunk_pages(pages: list[Page], title: str, max_chars: int = 600) -> list[Chunk]:
    """Split pages into chunks of whole lines, at most ~max_chars each.

    Every chunk starts with the document title ("contextual chunk header"), so a
    passage like "Q max 100 l/min" still says which product it belongs to when it
    is retrieved on its own.
    """
    chunks: list[Chunk] = []
    for page in pages:
        lines = [ln.strip() for ln in page.text.splitlines() if ln.strip()]
        buf: list[str] = []
        for line in lines:
            if buf and sum(len(x) + 1 for x in buf) + len(line) > max_chars:
                chunks.append(Chunk(page.number, len(chunks), _with_header(title, buf)))
                buf = buf[-1:]  # one line of overlap keeps context across the cut
            buf.append(line)
        if buf:
            chunks.append(Chunk(page.number, len(chunks), _with_header(title, buf)))
    return chunks


def _with_header(title: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    return body if lines and lines[0] == title else f"{title}\n{body}"
