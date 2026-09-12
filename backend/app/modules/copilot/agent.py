"""
app/modules/copilot/agent.py
==============================
AI Copilot — LangGraph agent over Groq (with model rotation).

Flow:  agent → tools → agent → … → extract_chart → END
                └→ nudge → agent   (once, when a chart was asked but not built)

The graph is built per-request with tools locked to the conversation's
dataset (make_tools). Tools are bound through the router's build_chain so the
fallback chain gets them on EVERY model (a bare `.bind_tools` on the fallback
runnable silently drops them). Chart configs travel on the mutable ctx, never
through the model's context — keeps token usage low and small models reliable.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, TypedDict

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.modules.admin.ai_usage import sum_langchain_usage
from app.modules.copilot.providers import (
    AllModelsRateLimitedError,
    GroqConfigError,
    get_router,
)
from app.modules.copilot.tools import CopilotContext, make_tools

logger = structlog.get_logger()

_SYSTEM_PROMPT = """You are InsightAI, a data analyst copilot for media buyers.
Answer questions about the user's dataset with tools — never guess numbers and never claim you lack access or diagnostics: call a tool instead.

Tools:
- chart_tool: REQUIRED for any chart/graph/plot request — one call runs the query and builds the chart (it attaches to your answer automatically).
- semantic_query_tool: numeric answers when no chart is wanted.
- sql_tool: raw row inspection (SELECT only).
- insight_tool: automated discovery (top performers, anomalies, trends).
- visualization_tool: chart from rows you already have (rare — prefer chart_tool).

Chart type by intent: ranking/comparison→bar; trend over time→line; cumulative→area; share of total→pie (exactly 1 measure + 1 dimension); correlation→scatter (exactly 2 measures, no dimension needed); single number→kpi (no dimension); volatility/open-high-low-close→candlestick (exactly 1 raw measure + time_dimension + granularity); row listing→table.
Raw measures (bare column names like spend) are row-level: only for candlestick or a raw line — never mix them with aggregated measures.

Rules:
1. If the user asks for any chart, call chart_tool BEFORE answering. Never reply "Got it" or promise a chart without calling it.
2. Prefer computed metrics (roas, ctr, cpa…) when they answer the question.
3. If a tool returns {{"error": ...}}, fix the arguments and call it again (max 2 retries). Never mention internal errors — deliver the corrected result.
4. Answer briefly: the key numbers plus one concrete recommendation.

Dimensions: {dimensions}
Measures: {measures}
"""

_AGG_SUFFIXES = {"_sum", "_avg", "_min", "_max"}

# Chart intent in the user's wording (EN + FR) — used only to decide whether
# the one-shot "nudge" retry applies when the model answers without a chart.
_CHART_INTENT = re.compile(
    r"\b(charts?|plot|graphs?|visuali[sz]\w*|candlestick|pie|donut|bar|line|area|"
    r"scatter|kpi|trend|courbes?|graphiques?|diagrammes?|camembert|bougies?)\b",
    re.IGNORECASE,
)


def _wants_chart(text: str) -> bool:
    return bool(_CHART_INTENT.search(text or ""))


def _format_members(members: dict) -> tuple[str, str]:
    """Compact member lists for the system prompt (token economy):
    aggregation variants collapse onto their raw base column."""
    dims = ", ".join(m["name"] for m in members.get("dimensions", [])) or "(none)"

    rows = members.get("measures", [])
    raw_bases = [
        m["name"] for m in rows
        if m.get("kind") == "measure" and m.get("agg") is None
    ]
    raw_set = set(raw_bases)

    def is_variant(name: str) -> bool:
        base, _, suffix = name.rpartition("_")
        return base in raw_set and f"_{suffix}" in _AGG_SUFFIXES

    others = [m["name"] for m in rows if m["name"] not in raw_set and not is_variant(m["name"])]

    parts = []
    if raw_bases:
        parts.append(
            f"columns (bare name = raw; append _sum/_avg/_min/_max to aggregate): {', '.join(raw_bases)}"
        )
    if others:
        parts.append(f"other measures: {', '.join(others)}")
    return dims, "; ".join(parts) or "(none)"


class AgentState(TypedDict):
    # add_messages APPENDS node returns to the transcript. Without it the
    # channel is replace-only and ToolNode wipes the history — the model then
    # sees an orphan tool result with no conversation and hallucinates.
    messages: Annotated[list, add_messages]
    echart_config: dict | None
    nudged: bool


def _build_graph(ctx: CopilotContext, llm_with_tools, tools: list, chart_wanted: bool) -> Any:
    tool_node = ToolNode(tools)

    dims, measures = _format_members(ctx.members)
    system_content = _SYSTEM_PROMPT.format(dimensions=dims, measures=measures)

    async def call_model(state: AgentState) -> dict:
        messages = [SystemMessage(content=system_content)] + state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        # The model answered without building the requested chart ("Got it"):
        # remind it once, then let it try again.
        if chart_wanted and ctx.last_echart_config is None and not state.get("nudged"):
            return "nudge"
        return "extract_chart"

    def nudge(state: AgentState) -> dict:
        reminder = HumanMessage(content=(
            "SYSTEM REMINDER: the user asked for a chart and none was created yet. "
            "Call chart_tool NOW with valid member names from the lists above. "
            "Do not answer again without calling it."
        ))
        logger.info("Copilot nudged to build the requested chart")
        return {"messages": [reminder], "nudged": True}

    def extract_chart(state: AgentState) -> dict:
        return {"echart_config": ctx.last_echart_config}

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.add_node("nudge", nudge)
    graph.add_node("extract_chart", extract_chart)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent", should_continue,
        {"tools": "tools", "nudge": "nudge", "extract_chart": "extract_chart"},
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("nudge", "agent")
    graph.add_edge("extract_chart", END)
    return graph.compile()


async def run_copilot(
    user_message: str,
    history: list[dict],
    ctx: CopilotContext,
) -> dict[str, Any]:
    """Run the copilot agent and return response text + chart + semantic query."""
    tools = make_tools(ctx)
    try:
        # Bind tools THROUGH the router: the fallback chain has no .bind_tools,
        # so binding must happen per-model before with_fallbacks wraps them.
        llm = await get_router().build_chain(bind_tools=tools)
    except AllModelsRateLimitedError as e:
        return {
            "text": f"The AI is temporarily rate-limited across all models. Please retry in about {e.retry_after}s.",
            "echart_config": None, "tool_calls": [], "semantic_query": None,
            "rate_limited": True,
        }
    except GroqConfigError as e:
        return {
            "text": f"AI is not configured: {e}. Set GROQ_API_KEY in the environment.",
            "echart_config": None, "tool_calls": [], "semantic_query": None,
        }

    graph = _build_graph(ctx, llm, tools, _wants_chart(user_message))

    messages: list = []
    for h in history[-10:]:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        elif h["role"] == "assistant":
            messages.append(AIMessage(content=h["content"]))
    messages.append(HumanMessage(content=user_message))

    state: AgentState = {"messages": messages, "echart_config": None, "nudged": False}

    try:
        result = await graph.ainvoke(state)
    except AllModelsRateLimitedError as e:
        return {
            "text": f"The AI hit rate limits on all models mid-request. Retry in ~{e.retry_after}s.",
            "echart_config": None, "tool_calls": [], "semantic_query": None,
            "rate_limited": True,
        }
    except Exception as e:
        logger.error("Copilot agent error", error=str(e))
        return {
            "text": f"I hit an error processing that request: {e}. Please rephrase.",
            "echart_config": None, "tool_calls": [], "semantic_query": None,
        }

    last_msg = result["messages"][-1]
    text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    if isinstance(text, list):  # some providers return content parts
        text = " ".join(str(p) for p in text)
    if not str(text).strip():
        text = (
            "Here is your chart." if result.get("echart_config")
            else "I couldn't complete that — please rephrase your request."
        )

    tool_calls_log = []
    for msg in result["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls_log.append({"tool": tc["name"], "args": tc.get("args", {})})

    return {
        "text": text,
        "echart_config": result.get("echart_config"),
        "tool_calls": tool_calls_log,
        "semantic_query": ctx.last_semantic_query,
        "usage": sum_langchain_usage(result["messages"]),
    }
