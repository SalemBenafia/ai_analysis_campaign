"""Copilot agent simulations — scripted LLM, zero real tokens, no rate-limit risk.

Replays the reported failure modes ("Got it" with no chart, hallucinated
"no access to diagnostics", rate-limited pool) and asserts the agent now
recovers: tools bound through the router, one-shot nudge, tool-error
self-correction, and token-economy guarantees.
"""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

import app.modules.copilot.agent as agent_mod
import app.modules.copilot.tools as tools_mod
from app.modules.copilot.agent import _format_members, _wants_chart, run_copilot
from app.modules.copilot.providers import AllModelsRateLimitedError
from app.modules.copilot.tools import CopilotContext

MEMBERS = {
    "dimensions": [
        {"name": "campaign", "kind": "dimension", "type": "string", "agg": None, "row_level": False},
        {"name": "date", "kind": "dimension", "type": "time", "agg": None, "row_level": False},
    ],
    "measures": [
        {"name": "spend", "kind": "measure", "agg": None, "row_level": True},
        {"name": "spend_sum", "kind": "measure", "agg": "SUM", "row_level": False},
        {"name": "revenue", "kind": "measure", "agg": None, "row_level": True},
        {"name": "revenue_sum", "kind": "measure", "agg": "SUM", "row_level": False},
        {"name": "row_count", "kind": "measure", "agg": "COUNT", "row_level": False},
        {"name": "roas", "kind": "computed", "agg": None, "row_level": False},
    ],
}


def _ctx() -> CopilotContext:
    return CopilotContext(
        dataset_id="00000000-0000-0000-0000-000000000000",
        dataset_table="t",
        allowed_columns={"campaign", "spend", "revenue"},
        cube_name="ds_test",
        members=MEMBERS,
        user_id="00000000-0000-0000-0000-000000000000",
    )


class ScriptedLLM:
    """Deterministic Groq stand-in: pops one scripted reply per agent turn."""

    def __init__(self, script: list[AIMessage]):
        self.script = list(script)
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        if not self.script:
            return AIMessage(content="(script exhausted)")
        return self.script.pop(0)


class StubRouter:
    def __init__(self, llm, rate_limited: bool = False):
        self.llm = llm
        self.rate_limited = rate_limited
        self.bound_tools = None

    async def build_chain(self, bind_tools=None):
        if self.rate_limited:
            raise AllModelsRateLimitedError(30)
        self.bound_tools = bind_tools
        return self.llm


def _tc(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


@pytest.fixture(autouse=True)
def fake_semantic(monkeypatch):
    """Offline semantic layer so no DB/LLM is touched."""
    async def fake_exec(ctx, query):
        rows = [{"campaign": "A", "spend_sum": 100}, {"campaign": "B", "spend_sum": 200}]
        if query.mode == "ohlc":
            rows = [{"date": "2025-01-01", "open": 1, "high": 3, "low": 0, "close": 2}]
        return {"rows": rows, "meta": {"engine": "duckdb", "took_ms": 1}}

    monkeypatch.setattr(tools_mod, "_execute_semantic_query", fake_exec)


def _install(monkeypatch, router: StubRouter) -> None:
    monkeypatch.setattr(agent_mod, "get_router", lambda: router)


class TestChartCreation:
    async def test_direct_chart_call(self, monkeypatch):
        llm = ScriptedLLM([
            _tc("chart_tool", {"chart_type": "bar", "measures": ["spend_sum"], "dimension": "campaign"}),
            AIMessage(content="Campaign B leads with 200 spend."),
        ])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        out = await run_copilot("show me spend by campaign as a bar chart", [], _ctx())
        assert out["echart_config"]["series"][0]["type"] == "bar"
        assert "200" in out["text"]
        assert [t["tool"] for t in out["tool_calls"]] == ["chart_tool"]

    async def test_tools_are_bound_through_the_router(self, monkeypatch):
        """Regression: tools must go through build_chain(bind_tools=...) — a
        bare .bind_tools on the fallback runnable silently drops them."""
        llm = ScriptedLLM([AIMessage(content="hello")])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        await run_copilot("hello", [], _ctx())
        assert router.bound_tools is not None
        assert {t.name for t in router.bound_tools} == {
            "chart_tool", "semantic_query_tool", "sql_tool", "insight_tool", "visualization_tool",
        }

    async def test_got_it_reply_gets_nudged_into_a_chart(self, monkeypatch):
        """The reported bug: model says 'Got it' and produces nothing."""
        llm = ScriptedLLM([
            AIMessage(content="Got it."),  # lazy reply, no tool call
            _tc("chart_tool", {"chart_type": "pie", "measures": ["revenue_sum"], "dimension": "campaign"}),
            AIMessage(content="Here is the revenue share per campaign."),
        ])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        out = await run_copilot("create a pie chart of revenue share per campaign", [], _ctx())
        assert out["echart_config"]["series"][0]["type"] == "pie"
        assert llm.calls == 3  # initial → nudge → final
        assert "Got it" not in out["text"]

    async def test_nudge_fires_only_once(self, monkeypatch):
        """A stubborn model that never calls tools ends cleanly (no loop)."""
        llm = ScriptedLLM([
            AIMessage(content="Got it."),
            AIMessage(content="Understood."),
        ])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        out = await run_copilot("plot spend please", [], _ctx())
        assert out["echart_config"] is None
        assert llm.calls == 2  # exactly one nudge, then stop

    async def test_no_chart_intent_no_nudge(self, monkeypatch):
        llm = ScriptedLLM([
            _tc("semantic_query_tool", {"measures": ["spend_sum"]}),
            AIMessage(content="Total spend is 300."),
        ])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        out = await run_copilot("what is total spend?", [], _ctx())
        assert out["echart_config"] is None
        assert llm.calls == 2  # no nudge turn
        assert "300" in out["text"]

    async def test_tool_error_self_correction(self, monkeypatch):
        """Invalid args → tool returns {"error": ...} → model retries with fixed args."""
        llm = ScriptedLLM([
            _tc("chart_tool", {"chart_type": "pie", "measures": ["spend_sum", "revenue_sum"], "dimension": "campaign"}),
            _tc("chart_tool", {"chart_type": "pie", "measures": ["spend_sum"], "dimension": "campaign"}, "c2"),
            AIMessage(content="Spend share: B has two thirds."),
        ])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        out = await run_copilot("pie chart of spend share", [], _ctx())
        assert out["echart_config"]["series"][0]["type"] == "pie"
        assert len([t for t in out["tool_calls"] if t["tool"] == "chart_tool"]) == 2

    async def test_empty_final_text_falls_back(self, monkeypatch):
        llm = ScriptedLLM([
            _tc("chart_tool", {"chart_type": "bar", "measures": ["spend_sum"], "dimension": "campaign"}),
            AIMessage(content=""),
        ])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        out = await run_copilot("bar chart of spend", [], _ctx())
        assert out["echart_config"] is not None
        assert out["text"] == "Here is your chart."


class TestRateLimits:
    async def test_all_models_rate_limited_is_a_clear_message(self, monkeypatch):
        router = StubRouter(ScriptedLLM([]), rate_limited=True)
        _install(monkeypatch, router)

        out = await run_copilot("bar chart of spend", [], _ctx())
        assert out.get("rate_limited") is True
        assert "rate-limited" in out["text"]
        assert out["echart_config"] is None
        assert router.llm.calls == 0  # zero wasted LLM calls


class TestTokenEconomy:
    def test_measures_collapse_onto_raw_bases(self):
        dims, measures = _format_members(MEMBERS)
        assert "campaign" in dims and "date" in dims
        # variants collapse: bases listed once, no *_sum spelled out
        assert "spend" in measures and "revenue" in measures
        assert "spend_sum" not in measures and "revenue_sum" not in measures
        assert "roas" in measures and "row_count" in measures

    def test_system_prompt_stays_small(self):
        dims, measures = _format_members(MEMBERS)
        prompt = agent_mod._SYSTEM_PROMPT.format(dimensions=dims, measures=measures)
        assert len(prompt) < 2600  # ~650 tokens — keeps every turn cheap

    def test_chart_intent_detection(self):
        assert _wants_chart("make me a PIE chart of revenue")
        assert _wants_chart("montre une courbe des dépenses")  # French
        assert _wants_chart("plot spend versus clicks")
        assert not _wants_chart("what is the total spend?")
        assert not _wants_chart("delete my dataset")

    async def test_chart_config_never_echoed_to_model(self, monkeypatch):
        """The ToolMessage the model reads must stay tiny (ack + sample)."""
        seen_tool_outputs: list[str] = []

        class RecordingLLM(ScriptedLLM):
            async def ainvoke(self, messages):
                for m in messages:
                    if m.__class__.__name__ == "ToolMessage":
                        seen_tool_outputs.append(str(m.content))
                return await super().ainvoke(messages)

        llm = RecordingLLM([
            _tc("chart_tool", {"chart_type": "bar", "measures": ["spend_sum"], "dimension": "campaign"}),
            AIMessage(content="Done."),
        ])
        router = StubRouter(llm)
        _install(monkeypatch, router)

        await run_copilot("bar chart of spend", [], _ctx())
        assert seen_tool_outputs, "tool output should reach the model"
        for content in seen_tool_outputs:
            parsed = json.loads(content)
            assert "series" not in content  # no full ECharts config
            assert parsed["chart_created"] == "bar"
            assert len(content) < 500  # tiny ack, not a payload
