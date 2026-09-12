"""
app/modules/admin/ai_usage.py
===============================
Token accounting for every LLM interaction. Recording must NEVER break the
feature that calls it — failures are logged and swallowed.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIUsageLog

logger = structlog.get_logger()


def sum_langchain_usage(messages: list[Any]) -> dict:
    """Aggregate token usage + model name from LangChain AIMessages."""
    input_tokens = 0
    output_tokens = 0
    model: str | None = None
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None)
        if usage:
            input_tokens += int(usage.get("input_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or 0)
        meta = getattr(msg, "response_metadata", None) or {}
        model = meta.get("model_name") or model
    return {"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens}


async def record_ai_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str | None,
    feature: str,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int | None = None,
    success: bool = True,
) -> None:
    try:
        db.add(AIUsageLog(
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            feature=feature,
            model=model,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            latency_ms=latency_ms,
            success=success,
        ))
        await db.commit()
    except Exception as e:
        logger.warning("Could not record AI usage", feature=feature, error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass
