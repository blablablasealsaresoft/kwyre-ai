"""
Shared AI Engine — Anthropic Claude API client for all Mint Rail products.

Provides async LLM inference with streaming support, retry logic, and
graceful fallback when no API key is configured.
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096


@dataclass
class AIResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class AIEngine:
    """Async Anthropic API client with retry and fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        default_system: str = "",
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.max_tokens = max_tokens
        self.default_system = default_system
        self._client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> AIResponse:
        if not self.available:
            return AIResponse(
                text="",
                model=self.model,
                error="No ANTHROPIC_API_KEY configured. Set the environment variable to enable AI features.",
            )

        sys_prompt = system or self.default_system
        use_model = model or self.model
        use_max = max_tokens or self.max_tokens

        body: dict = {
            "model": use_model,
            "max_tokens": use_max,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if sys_prompt:
            body["system"] = sys_prompt
        if tools:
            body["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        last_err = ""
        for attempt in range(3):
            try:
                client = await self._get_client()
                resp = await client.post(ANTHROPIC_API_URL, json=body, headers=headers)
                data = resp.json()

                if resp.status_code != 200:
                    err_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                    if resp.status_code == 429 and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return AIResponse(text="", model=use_model, error=err_msg)

                text_parts = [
                    block["text"]
                    for block in data.get("content", [])
                    if block.get("type") == "text"
                ]
                usage = data.get("usage", {})

                return AIResponse(
                    text="\n".join(text_parts),
                    model=use_model,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    stop_reason=data.get("stop_reason", ""),
                )

            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_err = str(exc)
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue

        return AIResponse(text="", model=use_model, error=f"Request failed after 3 attempts: {last_err}")

    async def analyze(
        self,
        domain: str,
        context: dict,
        system: str | None = None,
    ) -> AIResponse:
        """High-level helper: build a domain-specific prompt from context dict."""
        context_str = "\n".join(f"- {k}: {v}" for k, v in context.items() if v)
        prompt = f"Domain: {domain}\n\nContext:\n{context_str}\n\nProvide a thorough, expert-level analysis."
        return await self.complete(prompt, system=system)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
