"""
app/modules/insights/service.py
=================================
Executes a SavedInsight definition into rows + chart (+ optional AI
narrative), and turns a natural-language prompt into a validated insight
definition. Both run through the semantic layer.
"""
from __future__ import annotations

import json
import uuid
from typing import Literal, Union

import structlog
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SavedInsight, User
from app.modules.admin.ai_usage import record_ai_usage
from app.modules.semantic.registry import MemberCatalog, get_catalog
from app.modules.semantic.schemas import SemanticQuery, migrate_v1_definition
from app.modules.semantic.service import get_owned_dataset, run_semantic_query
from app.modules.visualization.chart_rules import RULE_HINTS, validate_definition
from app.modules.visualization.echarts import build_from_definition

logger = structlog.get_logger()


def definition_to_query(definition: dict, catalog: MemberCatalog) -> SemanticQuery:
    """
    Build a SemanticQuery from a (possibly legacy) insight definition,
    resolving legacy raw metric names to `<name>_sum` measures when needed.
    """
    was_v1 = definition.get("version") != 2
    d = migrate_v1_definition(definition)

    measures = []
    for m in d.get("measures", []):
        member = catalog.measures.get(m)
        if member is not None:
            # Legacy v1 metrics were raw column names meaning "sum of column" —
            # don't let them resolve to the new raw (unaggregated) members.
            if (
                was_v1
                and member.kind == "measure"
                and member.agg is None
                and f"{m}_sum" in catalog.measures
            ):
                measures.append(f"{m}_sum")
            else:
                measures.append(m)
        elif f"{m}_sum" in catalog.measures:
            measures.append(f"{m}_sum")
        else:
            measures.append(m)  # will fail validation with a clear error

    is_candlestick = str(d.get("visualization") or "").lower() == "candlestick"
    mode = "ohlc" if is_candlestick or d.get("mode") == "ohlc" else "auto"

    return SemanticQuery(
        measures=measures,
        dimensions=d.get("dimensions", []),
        time_dimension=d.get("time_dimension"),
        granularity=d.get("granularity"),
        date_range=d.get("date_range"),
        filters=d.get("filters", []),
        order=d.get("order", {}),
        limit=d.get("limit", 500),
        mode=mode,
    )


async def execute_insight(
    db: AsyncSession, user: User, insight: SavedInsight, explain: bool = False
) -> dict:
    if not insight.dataset_id:
        raise HTTPException(400, detail={"code": "NO_DATASET", "message": "Insight has no dataset."})

    ds = await get_owned_dataset(db, user, insight.dataset_id)
    catalog = await get_catalog(db, ds)

    definition = migrate_v1_definition(insight.insight_definition or {})
    query = definition_to_query(definition, catalog)
    result = await run_semantic_query(db, user, insight.dataset_id, query, catalog)
    rows = result["rows"]

    echart = build_from_definition(rows, {**definition, "title": insight.name})
    insight.echart_config = echart

    ai_explanation = None
    ai_recommendation = None
    if explain:
        ai_explanation, ai_recommendation = await _narrate(
            insight.name, definition, rows, db=db, user=user,
        )
        insight.ai_explanation = ai_explanation
        insight.ai_recommendation = ai_recommendation

    await db.commit()

    return {
        "rows": rows,
        "echart_config": echart,
        "definition": definition,
        "ai_explanation": ai_explanation,
        "ai_recommendation": ai_recommendation,
        "meta": result["meta"],
    }


async def _narrate(
    name: str, definition: dict, rows: list[dict],
    db: AsyncSession | None = None, user: User | None = None,
) -> tuple[str | None, str | None]:
    from app.modules.copilot.providers import get_router

    sample = rows[:15]
    prompt = (
        "You are a senior media-buying analyst. Given this insight and its data, "
        "write a concise explanation (2-3 sentences) and one concrete recommendation.\n\n"
        f"Insight: {name}\n"
        f"Definition: {json.dumps(definition)}\n"
        f"Data (first rows): {json.dumps(sample, default=str)}\n\n"
        'Respond as JSON: {"explanation": "...", "recommendation": "..."}'
    )
    usage: dict = {}
    try:
        text = await get_router().complete(prompt, usage_out=usage)
        data = _extract_json(text)
        return data.get("explanation"), data.get("recommendation")
    except Exception as e:
        logger.warning("Insight narration failed", error=str(e))
        return None, None
    finally:
        if db is not None and user is not None and usage:
            await record_ai_usage(
                db, user_id=user.id, feature="narrate",
                model=usage.get("model"),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )


class NLDefinition(BaseModel):
    """Typed shape the NL-create LLM answer must conform to."""

    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_dimension: str | None = None
    granularity: Literal["day", "week", "month"] | None = None
    date_range: Union[str, list[str], None] = None
    filters: list[dict] = Field(default_factory=list)
    order: dict[str, Literal["asc", "desc"]] = Field(default_factory=dict)
    limit: int = 50
    visualization: Literal[
        "bar", "line", "area", "pie", "scatter", "table", "kpi", "candlestick"
    ] = "bar"


_NL_CHART_GUIDE = (
    "Chart selection — pick `visualization` deliberately from the user's wording:\n"
    "- trend / evolution over time -> line ; cumulative volume over time -> area\n"
    "- share of total / percentage breakdown -> pie\n"
    "- correlation / relationship between two metrics -> scatter\n"
    "- single headline number / total -> kpi\n"
    "- volatility / range / open-high-low-close over time -> candlestick\n"
    "- ranking or comparison across categories -> bar\n"
    "- raw row listing -> table\n"
    "Shape requirements per type (violations are rejected):\n"
    + "\n".join(f"- {name}: {hint}" for name, hint in RULE_HINTS.items())
    + "\nRaw measures are the ones flagged raw:true (plain column names like 'spend'); "
    "every other chart type must use aggregated measures (e.g. 'spend_sum') or computed metrics."
)


def _parse_nl_definition(text: str, catalog: MemberCatalog) -> tuple[dict, list[str]]:
    """Parse + validate an LLM answer. Returns (definition, violation messages)."""
    try:
        raw = _extract_json(text)
    except ValueError as e:  # includes json.JSONDecodeError
        return {}, [f"answer was not valid JSON ({e})"]
    try:
        model = NLDefinition(**{k: v for k, v in raw.items() if k in NLDefinition.model_fields})
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        return {}, [f"invalid field {loc!r}: {first.get('msg', 'invalid')}"]

    definition = model.model_dump()
    messages = validate_definition(definition, catalog)

    unknown = [
        m for m in definition["measures"] + definition["dimensions"]
        if m not in catalog.measures and m not in catalog.dimensions
    ]
    if definition["time_dimension"] and definition["time_dimension"] not in catalog.dimensions:
        unknown.append(definition["time_dimension"])
    if unknown:
        messages.append(f"unknown members: {', '.join(unknown)} — use ONLY the listed members")

    return definition, messages


async def nl_to_definition(
    db: AsyncSession, user: User, dataset_id: uuid.UUID, nl_prompt: str
) -> dict:
    """Turn a natural-language request into a validated insight definition + preview."""
    from app.modules.copilot.providers import get_router

    ds = await get_owned_dataset(db, user, dataset_id)
    catalog = await get_catalog(db, ds)

    members = {
        "dimensions": [
            {"name": m.name, "type": m.type} for m in catalog.dimensions.values()
        ],
        "measures": [
            {"name": m.name, "raw": m.kind == "measure" and m.agg is None}
            for m in catalog.measures.values()
        ],
    }
    prompt = (
        "Convert the user's request into an InsightAI insight definition using ONLY "
        "the listed members. Respond as strict JSON with keys: measures (list), "
        "dimensions (list), time_dimension (string|null), granularity "
        "(day|week|month|null), date_range (string|null), filters (list of "
        '{member, operator, values}), order (object member->asc|desc), limit (int), '
        "visualization (bar|line|area|pie|scatter|table|kpi|candlestick).\n\n"
        f"{_NL_CHART_GUIDE}\n\n"
        f"Available members: {json.dumps(members)}\n\n"
        f"User request: {nl_prompt}\n\n"
        "JSON:"
    )
    usage: dict = {}
    try:
        text = await get_router().complete(prompt, usage_out=usage)
        definition, errors = _parse_nl_definition(text, catalog)
        if errors:
            logger.info("NL definition invalid — retrying once", errors=errors)
            retry_prompt = (
                f"{prompt}\n\nYour previous answer was rejected: {'; '.join(errors)}.\n"
                "Return corrected strict JSON only.\nJSON:"
            )
            text = await get_router().complete(retry_prompt, usage_out=usage)
            definition, errors = _parse_nl_definition(text, catalog)
            if errors:
                raise HTTPException(422, detail={
                    "code": "NL_DEFINITION_INVALID",
                    "message": "; ".join(errors),
                })
    finally:
        if usage:
            await record_ai_usage(
                db, user_id=user.id, feature="nl_create",
                model=usage.get("model"),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
    definition["version"] = 2

    query = definition_to_query(definition, catalog)
    result = await run_semantic_query(db, user, dataset_id, query, catalog)
    echart = build_from_definition(result["rows"], definition)

    return {
        "definition": definition,
        "rows": result["rows"],
        "echart_config": echart,
        "meta": result["meta"],
    }


def _extract_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        # strip a ```json ... ``` fence if present
        parts = text.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                text = candidate
                break
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start : end + 1])
