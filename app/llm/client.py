"""LLM + embedding client backed by an Ollama server.

Talks to the native Ollama endpoints:
  - POST /api/chat        for chat completions
  - POST /api/embeddings  for embeddings

A small JSON helper retries and repairs model output so the structured
extraction pipeline stays robust against the usual "model wrapped the JSON in
prose / markdown fences" failure modes.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings


class LLMError(RuntimeError):
    pass


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json_blob(text: str) -> str:
    """Best-effort extraction of a JSON object/array from raw model text."""
    text = text.strip()
    # strip <think> ... </think> reasoning blocks if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    fence = _JSON_FENCE.search(text)
    if fence:
        return fence.group(1).strip()

    # otherwise grab the outermost {...} or [...]
    start = None
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start is None:
        return text
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    for j in range(start, len(text)):
        if text[j] == opener:
            depth += 1
        elif text[j] == closer:
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return text[start:]


class LLMClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url
        self.chat_model = settings.chat_model
        self.embed_model = settings.embed_model
        self.timeout = settings.request_timeout
        headers = {}
        if settings.auth_token:
            headers["Authorization"] = f"Bearer {settings.auth_token}"
        self._client = httpx.Client(timeout=self.timeout, headers=headers)

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
            # ask the model to skip the reasoning trace where supported
            "think": False,
        }
        try:
            resp = self._client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise LLMError(f"chat request failed: {exc}") from exc
        data = resp.json()
        return (data.get("message") or {}).get("content", "") or ""

    def chat_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.1,
        retries: int = 2,
    ) -> Any:
        """Chat and parse the response as JSON, with repair + retry."""
        last_err: Exception | None = None
        cur_prompt = prompt
        for attempt in range(retries + 1):
            raw = self.chat(cur_prompt, system=system, temperature=temperature)
            blob = _extract_json_blob(raw)
            try:
                return json.loads(blob)
            except json.JSONDecodeError as exc:
                last_err = exc
                cur_prompt = (
                    prompt
                    + "\n\nYour previous answer was not valid JSON. "
                    "Return ONLY a single valid JSON value, no prose, no markdown fences."
                )
        raise LLMError(f"could not parse JSON after {retries + 1} attempts: {last_err}")

    # ------------------------------------------------------------- embeddings
    def embed(self, text: str) -> list[float]:
        payload = {"model": self.embed_model, "prompt": text}
        try:
            resp = self._client.post(f"{self.base_url}/api/embeddings", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise LLMError(f"embedding request failed: {exc}") from exc
        emb = resp.json().get("embedding")
        if not emb:
            raise LLMError("embedding response had no 'embedding' field")
        return emb

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def health(self) -> dict[str, Any]:
        """Quick reachability probe used by the API /health route."""
        info: dict[str, Any] = {"base_url": self.base_url, "ok": False}
        try:
            resp = self._client.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m.get("name") for m in resp.json().get("models", [])]
            info.update(ok=True, models=models)
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)
        return info


llm = LLMClient()
