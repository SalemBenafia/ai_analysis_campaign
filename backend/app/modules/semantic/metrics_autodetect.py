"""
app/modules/semantic/metrics_autodetect.py
============================================
Auto-creates marketing computed metrics (ROAS, CTR, CPA, CPM, CPC, AOV,
CVR) when a dataset's columns match well-known patterns. Users can edit or
delete these later — they are flagged is_auto.
"""
from __future__ import annotations

import re

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Dataset, DatasetColumn, SemanticMetric

logger = structlog.get_logger()

_PATTERNS = {
    "spend": r"^(spend|cost|amount_spent|ad_spend)",
    "revenue": r"^(revenue|purchase_value|conversion_value|purchases_value|sales|total_revenue)",
    "impressions": r"^(impressions?|imps?)$",
    "clicks": r"^(clicks?|link_clicks?)$",
    "purchases": r"^(purchases?|conversions?|orders?|results?)$",
}


def _find(columns: list[DatasetColumn], role: str) -> str | None:
    pattern = re.compile(_PATTERNS[role], re.IGNORECASE)
    for col in columns:
        if col.is_metric and pattern.match(col.semantic_name or col.name):
            return col.semantic_name or col.name
    return None


def _ratio(num: str, den: str, multiplier: float = 1) -> dict:
    expr: dict = {
        "type": "ratio",
        "numerator": {"agg": "sum", "column": num},
        "denominator": {"agg": "sum", "column": den},
    }
    if multiplier != 1:
        expr["multiplier"] = multiplier
    return expr


def detect_metric_definitions(columns: list[DatasetColumn]) -> list[dict]:
    spend = _find(columns, "spend")
    revenue = _find(columns, "revenue")
    impressions = _find(columns, "impressions")
    clicks = _find(columns, "clicks")
    purchases = _find(columns, "purchases")

    defs: list[dict] = []
    if revenue and spend:
        defs.append({
            "name": "roas", "display_name": "ROAS", "format": "number",
            "description": "Return on ad spend: revenue / spend",
            "expression": _ratio(revenue, spend),
        })
    if clicks and impressions:
        defs.append({
            "name": "ctr", "display_name": "CTR %", "format": "percent",
            "description": "Click-through rate: clicks / impressions × 100",
            "expression": _ratio(clicks, impressions, 100),
        })
    if spend and purchases:
        defs.append({
            "name": "cpa", "display_name": "CPA", "format": "currency",
            "description": "Cost per acquisition: spend / purchases",
            "expression": _ratio(spend, purchases),
        })
    if spend and impressions:
        defs.append({
            "name": "cpm", "display_name": "CPM", "format": "currency",
            "description": "Cost per 1000 impressions",
            "expression": _ratio(spend, impressions, 1000),
        })
    if spend and clicks:
        defs.append({
            "name": "cpc", "display_name": "CPC", "format": "currency",
            "description": "Cost per click: spend / clicks",
            "expression": _ratio(spend, clicks),
        })
    if revenue and purchases:
        defs.append({
            "name": "aov", "display_name": "AOV", "format": "currency",
            "description": "Average order value: revenue / purchases",
            "expression": _ratio(revenue, purchases),
        })
    if purchases and clicks:
        defs.append({
            "name": "cvr", "display_name": "CVR %", "format": "percent",
            "description": "Conversion rate: purchases / clicks × 100",
            "expression": _ratio(purchases, clicks, 100),
        })
    return defs


async def autodetect_metrics(
    db: AsyncSession, dataset: Dataset, columns: list[DatasetColumn]
) -> int:
    """Create auto metrics that don't already exist. Returns count created."""
    existing_result = await db.execute(
        select(SemanticMetric.name).where(SemanticMetric.dataset_id == dataset.id)
    )
    existing = {row[0] for row in existing_result.all()}

    created = 0
    for definition in detect_metric_definitions(columns):
        if definition["name"] in existing:
            continue
        db.add(SemanticMetric(dataset_id=dataset.id, is_auto=True, **definition))
        created += 1

    if created:
        await db.commit()
        logger.info("Auto metrics created", dataset_id=str(dataset.id), count=created)
    return created
