"""Settings, read from environment variables (or a .env file you export yourself)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = _env("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/matcher")
    # "hashing": offline, deterministic, no model needed (tests, CI)
    # "ollama":  real semantic embeddings, e.g. nomic-embed-text (768 dims)
    embedder: str = _env("EMBEDDER", "hashing")
    # "regex": label-based baseline, "llm": LLM with JSON-schema output (regex fills gaps)
    extractor: str = _env("EXTRACTOR", "regex")
    ollama_url: str = _env("OLLAMA_URL", "http://localhost:11434")
    llm_model: str = _env("LLM_MODEL", "qwen2.5:7b")
    embed_model: str = _env("EMBED_MODEL", "nomic-embed-text")
    # Use the LLM to write RAG answers. Without it, answers are the best cited passages.
    rag_llm: bool = _env("RAG_LLM", "false").lower() == "true"

    @property
    def embed_dim(self) -> int:
        if self.embedder == "ollama":
            return int(_env("EMBED_DIM", "768"))
        return 384


settings = Settings()
