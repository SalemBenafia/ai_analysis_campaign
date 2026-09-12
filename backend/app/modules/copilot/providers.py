"""
app/modules/copilot/providers.py
==================================
Groq-only LLM provider with automatic model rotation.

GROQ_MODELS is an ordered pool. When a model returns a 429 it is put on a
Redis cooldown (TTL from the `retry-after` header, else GROQ_COOLDOWN_SECONDS)
and the next model in the pool takes over — for both tool-calling agent runs
(via LangChain `.with_fallbacks`) and one-shot completions. Editing the pool
env var is all that's needed to track Groq's free-tier lineup.
"""
from __future__ import annotations

import asyncio

import structlog
from langchain_core.language_models import BaseChatModel

from app.core.redis import get_redis
from app.core.settings import settings

logger = structlog.get_logger()

_COOLDOWN_PREFIX = "groq:cooldown:"


class AllModelsRateLimitedError(RuntimeError):
    """Every model in the pool is currently on cooldown."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"All Groq models rate-limited. Retry in ~{retry_after}s.")


class GroqConfigError(RuntimeError):
    """Groq is not configured (missing API key or empty model pool)."""


def _is_rate_limit(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    name = exc.__class__.__name__.lower()
    return "ratelimit" in name or "429" in str(exc)


def _retry_after_seconds(exc: BaseException) -> int:
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw:
            try:
                return max(1, int(float(raw)))
            except (TypeError, ValueError):
                pass
    return settings.GROQ_COOLDOWN_SECONDS


class GroqModelRouter:
    """Chooses active Groq models, tracks cooldowns, builds LLM chains."""

    def __init__(self) -> None:
        self._pool = settings.groq_model_pool

    def _make_llm(self, model: str) -> BaseChatModel:
        from langchain_groq import ChatGroq

        if not settings.GROQ_API_KEY:
            raise GroqConfigError("GROQ_API_KEY is not configured")
        return ChatGroq(
            model=model,
            api_key=settings.GROQ_API_KEY,
            temperature=0.1,
            max_tokens=settings.GROQ_MAX_TOKENS,
            timeout=settings.GROQ_REQUEST_TIMEOUT,
            max_retries=0,  # rotation handles retries, not the SDK
        )

    async def get_active_models(self) -> list[str]:
        if not self._pool:
            raise GroqConfigError("GROQ_MODELS pool is empty")
        try:
            redis = get_redis()
            cooling = {
                m for m in self._pool
                if await redis.get(f"{_COOLDOWN_PREFIX}{m}")
            }
        except Exception:
            cooling = set()
        active = [m for m in self._pool if m not in cooling]
        return active or []

    async def cooldown_ttl(self) -> int:
        """Smallest remaining cooldown across the pool (for 503 retry hints)."""
        try:
            redis = get_redis()
            ttls = []
            for m in self._pool:
                ttl = await redis.ttl(f"{_COOLDOWN_PREFIX}{m}")
                if ttl and ttl > 0:
                    ttls.append(ttl)
            return min(ttls) if ttls else settings.GROQ_COOLDOWN_SECONDS
        except Exception:
            return settings.GROQ_COOLDOWN_SECONDS

    async def mark_cooldown(self, model: str, seconds: int) -> None:
        try:
            await get_redis().set(f"{_COOLDOWN_PREFIX}{model}", "1", ex=seconds)
            logger.warning("Groq model cooling down", model=model, seconds=seconds)
        except Exception as e:
            logger.debug("Could not set cooldown", model=model, error=str(e))

    async def build_chain(self, bind_tools=None) -> BaseChatModel:
        """
        Build a runnable: the first active model with the rest as fallbacks.
        `bind_tools` is an optional list of tools to bind to each model.
        """
        active = await self.get_active_models()
        if not active:
            raise AllModelsRateLimitedError(await self.cooldown_ttl())

        def prep(model: str):
            llm = self._make_llm(model)
            return llm.bind_tools(bind_tools) if bind_tools else llm

        primary = prep(active[0])
        fallbacks = [prep(m) for m in active[1:]]
        return primary.with_fallbacks(fallbacks) if fallbacks else primary

    async def complete(self, prompt: str, usage_out: dict | None = None) -> str:
        """
        One-shot completion with rotation. Tries each active model in turn,
        marking rate-limited ones on cooldown.
        usage_out: optional dict that ACCUMULATES token usage across calls
        (pass the same dict for a retry loop, then record it once).
        """
        active = await self.get_active_models()
        if not active:
            raise AllModelsRateLimitedError(await self.cooldown_ttl())

        last_exc: BaseException | None = None
        for model in active:
            llm = self._make_llm(model)
            try:
                resp = await llm.ainvoke(prompt)
                if usage_out is not None:
                    usage = getattr(resp, "usage_metadata", None) or {}
                    usage_out["model"] = model
                    usage_out["input_tokens"] = usage_out.get("input_tokens", 0) + int(usage.get("input_tokens") or 0)
                    usage_out["output_tokens"] = usage_out.get("output_tokens", 0) + int(usage.get("output_tokens") or 0)
                return resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:  # noqa: BLE001 — need to inspect all provider errors
                last_exc = e
                if _is_rate_limit(e):
                    await self.mark_cooldown(model, _retry_after_seconds(e))
                    continue
                raise
        if last_exc and _is_rate_limit(last_exc):
            raise AllModelsRateLimitedError(await self.cooldown_ttl())
        if last_exc:
            raise last_exc
        raise GroqConfigError("No Groq model produced a response")


_router: GroqModelRouter | None = None


def get_router() -> GroqModelRouter:
    global _router
    if _router is None:
        _router = GroqModelRouter()
    return _router
