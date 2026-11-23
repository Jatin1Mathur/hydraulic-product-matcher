"""Minimal Ollama client (chat + embeddings). Runs fully local: no data leaves the machine."""

from __future__ import annotations

from typing import Any

import httpx


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self, base_url: str, model: str, timeout: float = 120.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.model = model
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def chat(
        self, messages: list[dict[str, str]], schema: dict[str, Any] | None = None, temperature: float = 0.0
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if schema is not None:
            body["format"] = schema  # Ollama constrains the output to this JSON schema
        try:
            resp = self._http.post("/api/chat", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama chat failed: {exc}. Is `ollama serve` running?") from exc
        content = resp.json().get("message", {}).get("content")
        if not content:
            raise LLMError("Ollama returned an empty answer")
        return content

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        try:
            resp = self._http.post("/api/embed", json={"model": model, "input": texts})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama embed failed: {exc}. Did you `ollama pull {model}`?") from exc
        return resp.json()["embeddings"]
