"""Text embeddings.

OllamaEmbedder   real semantic embeddings from a local model (default nomic-embed-text).
                 Knows that "LS control" and "load sensing regulator" mean the same thing.
HashingEmbedder  offline fallback for tests and CI. Hashes words and character
                 n-grams into a fixed-size vector, so it captures spelling overlap
                 ("load-sensing" ~ "load sensing") but not meaning. No download needed.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

from hpm.config import Settings
from hpm.llm import OllamaClient


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _l2(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        feats = [f"w:{w}" for w in words]
        for w in words:
            padded = f"#{w}#"
            feats += [f"c:{padded[i : i + n]}" for n in (3, 4) for i in range(len(padded) - n + 1)]
        return feats

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for f in self._features(text):
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            v[h % self.dim] += (1.0 if (h >> 63) & 1 else -1.0) * (2.0 if f.startswith("w:") else 1.0)
        return v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return _l2(np.stack([self._vec(t) for t in texts])) if texts else np.zeros((0, self.dim))

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


class OllamaEmbedder:
    name = "ollama"

    def __init__(self, client: OllamaClient, model: str, dim: int) -> None:
        self.client, self.model, self.dim = client, model, dim
        # nomic-embed-text was trained with task prefixes; using them improves retrieval
        self._nomic = "nomic" in model

    def _embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), 32):
            out += self.client.embed(texts[i : i + 32], self.model)
        m = np.asarray(out, dtype=np.float32)
        if m.shape[1] != self.dim:
            raise ValueError(f"{self.model} returns {m.shape[1]} dims, database expects {self.dim} (set EMBED_DIM)")
        return _l2(m)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed([f"search_document: {t}" if self._nomic else t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([f"search_query: {text}" if self._nomic else text])[0]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if d == 0 or math.isnan(d) else float(np.dot(a, b) / d)


def make_embedder(s: Settings) -> Embedder:
    if s.embedder == "ollama":
        return OllamaEmbedder(OllamaClient(s.ollama_url, s.llm_model), s.embed_model, s.embed_dim)
    return HashingEmbedder(s.embed_dim)
