"""Groq model router: cooldown detection, rotation, one-shot completion."""
from __future__ import annotations

import pytest

from app.core.settings import settings
from app.modules.copilot import providers
from app.modules.copilot.providers import (
    AllModelsRateLimitedError,
    GroqModelRouter,
    _is_rate_limit,
    _retry_after_seconds,
)


class FakeRateLimit(Exception):
    status_code = 429

    class response:
        headers = {"retry-after": "42"}


class FakeOther(Exception):
    status_code = 500


class TestRateLimitDetection:
    def test_429_detected(self):
        assert _is_rate_limit(FakeRateLimit())

    def test_name_based_detection(self):
        class RateLimitError(Exception):
            pass
        assert _is_rate_limit(RateLimitError())

    def test_non_rate_limit(self):
        assert not _is_rate_limit(FakeOther())

    def test_retry_after_from_header(self):
        assert _retry_after_seconds(FakeRateLimit()) == 42

    def test_retry_after_default(self):
        assert _retry_after_seconds(FakeOther()) == settings.GROQ_COOLDOWN_SECONDS


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def ttl(self, key):
        return 30 if key in self.store else -2


@pytest.fixture()
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(providers, "get_redis", lambda: redis)
    return redis


@pytest.fixture()
def router(monkeypatch):
    monkeypatch.setattr(
        settings, "GROQ_MODELS", "model-a,model-b,model-c", raising=False
    )
    r = GroqModelRouter()
    r._pool = ["model-a", "model-b", "model-c"]
    return r


class TestActiveModels:
    async def test_all_active_when_no_cooldown(self, router, fake_redis):
        assert await router.get_active_models() == ["model-a", "model-b", "model-c"]

    async def test_cooling_model_excluded(self, router, fake_redis):
        await router.mark_cooldown("model-a", 30)
        assert await router.get_active_models() == ["model-b", "model-c"]

    async def test_all_cooling_returns_empty(self, router, fake_redis):
        for m in router._pool:
            await router.mark_cooldown(m, 30)
        assert await router.get_active_models() == []


class TestBuildChain:
    async def test_tools_bound_on_every_model_before_fallback_wrap(
        self, router, fake_redis, monkeypatch
    ):
        """Regression for the copilot 'Got it' bug: the fallback runnable has
        no .bind_tools, so binding must happen per-model inside build_chain."""
        made = []

        class FakeBindable:
            def __init__(self, model):
                self.model = model
                self.bound = None
                made.append(self)

            def bind_tools(self, tools):
                self.bound = tools
                return self

            def with_fallbacks(self, fallbacks):
                self.fallbacks = fallbacks
                return self

        monkeypatch.setattr(router, "_make_llm", lambda m: FakeBindable(m))
        tools = ["tool-a", "tool-b"]
        chain = await router.build_chain(bind_tools=tools)

        assert len(made) == 3  # one per active model
        assert all(llm.bound == tools for llm in made)
        assert chain is made[0] and len(chain.fallbacks) == 2


class TestComplete:
    async def test_rotates_past_rate_limited_model(self, router, fake_redis, monkeypatch):
        calls = []

        class FakeLLM:
            def __init__(self, model):
                self.model = model

            async def ainvoke(self, prompt):
                calls.append(self.model)
                if self.model == "model-a":
                    raise FakeRateLimit()

                class R:
                    content = f"answer from {self.model}"
                return R()

        monkeypatch.setattr(router, "_make_llm", lambda m: FakeLLM(m))
        result = await router.complete("hi")
        assert result == "answer from model-b"
        assert calls == ["model-a", "model-b"]
        # model-a should now be on cooldown
        assert "model-a" not in await router.get_active_models()

    async def test_all_rate_limited_raises(self, router, fake_redis, monkeypatch):
        class FakeLLM:
            def __init__(self, model):
                self.model = model

            async def ainvoke(self, prompt):
                raise FakeRateLimit()

        monkeypatch.setattr(router, "_make_llm", lambda m: FakeLLM(m))
        with pytest.raises(AllModelsRateLimitedError):
            await router.complete("hi")

    async def test_non_rate_limit_error_propagates(self, router, fake_redis, monkeypatch):
        class FakeLLM:
            def __init__(self, model):
                self.model = model

            async def ainvoke(self, prompt):
                raise FakeOther("boom")

        monkeypatch.setattr(router, "_make_llm", lambda m: FakeLLM(m))
        with pytest.raises(FakeOther):
            await router.complete("hi")
