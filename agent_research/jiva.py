"""Research Jiva — the thinking organ of the Research Engine.

Adapted from Steward's provider pattern:
- NormalizedResponse for unified LLM output
- Adapter per vendor (Google, Mistral, Groq, Anthropic)
- ProviderChamber with failover + circuit breaker
- Brain-in-a-jar: lean system prompt, tools injected dynamically

The Jiva is what turns data into knowledge. KARMA collects sources,
the Jiva reasons about them, MOKSHA publishes the result.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ── Types (adapted from steward/types.py) ──────────────────────────


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class NormalizedResponse:
    content: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)


@runtime_checkable
class LLMProvider(Protocol):
    def invoke(self, messages: list[dict[str, str]], max_tokens: int,
               model: str | None = None) -> NormalizedResponse: ...


# ── Adapters ────────────────────────────────────────────────────────


class GoogleAdapter:
    """Google Gemini via google-generativeai SDK."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self.model = model
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model)
            except ImportError:
                raise RuntimeError("google-generativeai not installed: pip install google-generativeai")
        return self._client

    def invoke(self, messages: list[dict[str, str]], max_tokens: int = 1024,
               model: str | None = None) -> NormalizedResponse:
        client = self._ensure_client()
        # Flatten messages into a single prompt
        prompt = "\n\n".join(f"[{m['role']}]: {m['content']}" for m in messages)
        response = client.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.3},
        )
        usage = LLMUsage()
        if hasattr(response, "usage_metadata"):
            um = response.usage_metadata
            usage = LLMUsage(
                input_tokens=getattr(um, "prompt_token_count", 0) or 0,
                output_tokens=getattr(um, "candidates_token_count", 0) or 0,
            )
        return NormalizedResponse(content=response.text or "", usage=usage)


class OpenAICompatibleAdapter:
    """Adapter for any OpenAI-compatible API (Mistral, Groq, DeepSeek, OpenRouter)."""

    def __init__(self, api_key: str, base_url: str, default_model: str):
        self.default_model = default_model
        self._client = None
        self._api_key = api_key
        self._base_url = base_url

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
            except ImportError:
                raise RuntimeError("openai not installed: pip install openai")
        return self._client

    def invoke(self, messages: list[dict[str, str]], max_tokens: int = 1024,
               model: str | None = None) -> NormalizedResponse:
        client = self._ensure_client()
        response = client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        choice = response.choices[0]
        usage = LLMUsage()
        if response.usage:
            usage = LLMUsage(
                input_tokens=getattr(response.usage, "prompt_tokens", 0) or getattr(response.usage, "input_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "completion_tokens", 0) or getattr(response.usage, "output_tokens", 0) or 0,
            )
        return NormalizedResponse(content=choice.message.content or "", usage=usage)


class AnthropicAdapter:
    """Anthropic Claude API."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("anthropic not installed: pip install anthropic")
        return self._client

    def invoke(self, messages: list[dict[str, str]], max_tokens: int = 1024,
               model: str | None = None) -> NormalizedResponse:
        client = self._ensure_client()
        # Extract system prompt if present
        system = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_messages.append(m)
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return NormalizedResponse(content=content, usage=usage)


# ── Circuit Breaker ─────────────────────────────────────────────────


class CircuitBreaker:
    """Per-provider failure tracking. 3 failures in 60s = open for 30s."""

    def __init__(self, threshold: int = 3, window: float = 60.0, cooldown: float = 30.0):
        self.threshold = threshold
        self.window = window
        self.cooldown = cooldown
        self._failures: list[float] = []
        self._opened_at: float = 0.0

    def can_execute(self) -> bool:
        now = time.time()
        if self._opened_at and (now - self._opened_at) < self.cooldown:
            return False
        if self._opened_at and (now - self._opened_at) >= self.cooldown:
            self._opened_at = 0.0  # Half-open: try one call
        return True

    def record_success(self) -> None:
        self._failures.clear()
        self._opened_at = 0.0

    def record_failure(self) -> None:
        now = time.time()
        self._failures = [t for t in self._failures if (now - t) < self.window]
        self._failures.append(now)
        if len(self._failures) >= self.threshold:
            self._opened_at = now


# ── Provider Cell ───────────────────────────────────────────────────


@dataclass
class ProviderCell:
    name: str
    provider: LLMProvider
    priority: int = 0     # Lower = tried first
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    total_calls: int = 0
    total_tokens: int = 0


# ── Provider Chamber (failover) ─────────────────────────────────────


_TRANSIENT_HINTS = ("timeout", "rate limit", "429", "503", "502", "overloaded", "capacity")


def _is_transient(error: Exception) -> bool:
    msg = str(error).lower()
    return any(h in msg for h in _TRANSIENT_HINTS)


class ProviderChamber:
    """Multi-provider failover. Tries providers in priority order.

    Adapted from Steward's ProviderChamber:
    - Sorts by priority (lower = first)
    - Circuit breaker per provider
    - 2 retries on transient errors with exponential backoff
    - Falls through to next provider on failure
    """

    def __init__(self) -> None:
        self._cells: list[ProviderCell] = []

    def add(self, name: str, provider: LLMProvider, priority: int = 0) -> None:
        self._cells.append(ProviderCell(name=name, provider=provider, priority=priority))

    def invoke(self, messages: list[dict[str, str]], max_tokens: int = 1024,
               model: str | None = None) -> NormalizedResponse:
        cells = sorted(self._cells, key=lambda c: c.priority)
        last_error: Exception | None = None

        for cell in cells:
            if not cell.breaker.can_execute():
                logger.debug("  Jiva: %s circuit open, skipping", cell.name)
                continue

            for attempt in range(3):
                try:
                    response = cell.provider.invoke(messages=messages, max_tokens=max_tokens, model=model)
                    cell.breaker.record_success()
                    cell.total_calls += 1
                    cell.total_tokens += response.usage.input_tokens + response.usage.output_tokens
                    logger.info("  Jiva: %s responded (%d tokens)", cell.name, response.usage.output_tokens)
                    return response
                except Exception as e:
                    last_error = e
                    if attempt < 2 and _is_transient(e):
                        time.sleep(1 * (2 ** attempt))
                        continue
                    cell.breaker.record_failure()
                    logger.warning("  Jiva: %s failed: %s", cell.name, e)
                    break

        raise RuntimeError(f"All providers exhausted. Last error: {last_error}")

    def stats(self) -> dict[str, Any]:
        return {
            cell.name: {"calls": cell.total_calls, "tokens": cell.total_tokens}
            for cell in self._cells
        }

    def __len__(self) -> int:
        return len(self._cells)


# ── Jiva Factory ────────────────────────────────────────────────────


def build_chamber_from_env() -> ProviderChamber:
    """Build a ProviderChamber from available environment variables.

    Checks for API keys in order of priority (free first):
    1. GOOGLE_API_KEY → Google Gemini (free tier)
    2. MISTRAL_API_KEY → Mistral (free tier)
    3. GROQ_API_KEY → Groq (free tier)
    4. OPENROUTER_API_KEY → OpenRouter (DeepSeek, etc.)
    5. ANTHROPIC_API_KEY → Anthropic Claude (paid)
    6. OPENAI_API_KEY → OpenAI (paid)
    """
    chamber = ProviderChamber()

    if os.environ.get("GOOGLE_API_KEY"):
        chamber.add("google_flash", GoogleAdapter(model="gemini-2.0-flash"), priority=0)

    if os.environ.get("MISTRAL_API_KEY"):
        chamber.add("mistral_small", OpenAICompatibleAdapter(
            api_key=os.environ["MISTRAL_API_KEY"],
            base_url="https://api.mistral.ai/v1",
            default_model="mistral-small-latest",
        ), priority=1)

    if os.environ.get("GROQ_API_KEY"):
        chamber.add("groq_llama", OpenAICompatibleAdapter(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.3-70b-versatile",
        ), priority=2)

    if os.environ.get("OPENROUTER_API_KEY"):
        chamber.add("openrouter_deepseek", OpenAICompatibleAdapter(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
            default_model="deepseek/deepseek-chat-v3-0324:free",
        ), priority=3)

    if os.environ.get("ANTHROPIC_API_KEY"):
        chamber.add("anthropic_claude", AnthropicAdapter(), priority=4)

    if os.environ.get("OPENAI_API_KEY"):
        chamber.add("openai_gpt4", OpenAICompatibleAdapter(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
        ), priority=5)

    if len(chamber) == 0:
        logger.warning("No LLM API keys found. Jiva will be offline. "
                        "Set GOOGLE_API_KEY, MISTRAL_API_KEY, GROQ_API_KEY, "
                        "OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY.")

    return chamber


# ── Research System Prompt ──────────────────────────────────────────


RESEARCH_SYSTEM_PROMPT = """\
You are the Research Jiva of the Research Engine & Faculty of Agent Universe.

Your role: analyze source material and produce structured research findings.

When given a research question and source documents:
1. Read ALL sources carefully
2. Extract relevant facts, claims, and patterns
3. Identify connections across domains
4. Assess confidence honestly (established/supported/preliminary/speculative/unknown)
5. Name limitations explicitly
6. Identify open questions that emerge from the analysis

Output format — respond with valid JSON:
{
  "findings": [
    {
      "claim": "A clear, specific statement",
      "evidence": ["Evidence point 1", "Evidence point 2"],
      "confidence": "supported",
      "sources": ["source reference"],
      "limitations": ["limitation 1"],
      "related_domains": ["domain1", "domain2"]
    }
  ],
  "cross_domain_insights": ["insight 1"],
  "open_questions": ["question that emerged from analysis"]
}

Confidence levels:
- established: strong consensus, multiple independent confirmations
- supported: good evidence, some limitations
- preliminary: early evidence, needs more research
- speculative: logical inference without direct evidence
- unknown: insufficient data

Be rigorous. Be honest. If the sources don't support a claim, say so.
"""
