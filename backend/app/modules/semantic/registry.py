"""
app/modules/semantic/registry.py
==================================
Member catalog for a dataset (dimensions + measures, including computed
metrics) and validation/resolution of SemanticQueries against it.

The registry owns the bidirectional mapping between:
  - semantic names (snake_case — used in marts parquet, Cube and the API), and
  - original column names (used by the local DuckDB table).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.core.settings import settings
from app.db.models import ColumnType, Dataset, DatasetColumn, SemanticMetric
from app.modules.semantic.formula import expression_is_row_level

logger = structlog.get_logger()

SCHEMA_VERSION_KEY = "cube:schema_version"

_COL_MEASURE_SUFFIXES = {"sum": "sum", "avg": "avg", "min": "min", "max": "max"}


class UnknownMemberError(ValueError):
    """A query referenced a member not in the dataset's catalog."""


@dataclass
class Member:
    name: str                      # semantic member name (e.g. "spend_sum", "campaign", "roas")
    kind: str                      # "dimension" | "measure" | "computed"
    title: str = ""
    type: str = "string"           # dimension: string|time|number|boolean ; measure: number
    column: str | None = None      # original column name (None for computed/row_count)
    semantic_column: str | None = None  # snake_case column in marts parquet
    agg: str | None = None         # SUM/AVG/... for column measures
    expression: dict | None = None  # for computed metrics
    format: str | None = None
    description: str | None = None
    row_level: bool = False        # raw column measure or row-level formula (DuckDB detail only)


@dataclass
class MemberCatalog:
    cube_name: str
    dimensions: dict[str, Member] = field(default_factory=dict)
    measures: dict[str, Member] = field(default_factory=dict)

    def get(self, name: str) -> Member:
        member = self.dimensions.get(name) or self.measures.get(name)
        if member is None:
            raise UnknownMemberError(f"Unknown member: {name!r}")
        return member

    def as_dict(self) -> dict[str, Any]:
        def row(m: Member) -> dict:
            return {
                "name": m.name, "kind": m.kind, "title": m.title, "type": m.type,
                "column": m.column, "format": m.format, "description": m.description,
                "agg": m.agg, "row_level": m.row_level,
            }
        return {
            "cube": self.cube_name,
            "dimensions": [row(m) for m in self.dimensions.values()],
            "measures": [row(m) for m in self.measures.values()],
        }


def cube_name_for(dataset: Dataset) -> str:
    return f"ds_{str(dataset.id).replace('-', '')[:8]}"


_DIM_TYPE_BY_COL = {
    ColumnType.TEXT: "string",
    ColumnType.DATE: "time",
    ColumnType.DATETIME: "time",
    ColumnType.BOOLEAN: "boolean",
    ColumnType.INTEGER: "number",
    ColumnType.FLOAT: "number",
}


def build_catalog(
    dataset: Dataset,
    columns: list[DatasetColumn],
    metrics: list[SemanticMetric],
) -> MemberCatalog:
    catalog = MemberCatalog(cube_name=cube_name_for(dataset))

    for col in columns:
        sem = col.semantic_name or col.name
        if col.is_dimension:
            catalog.dimensions[sem] = Member(
                name=sem, kind="dimension",
                title=col.display_name,
                type=_DIM_TYPE_BY_COL.get(col.col_type, "string"),
                column=col.name, semantic_column=sem,
            )
        if col.is_metric:
            # Raw member first (agg=None): true row-level values. Skipped when
            # the same name is already a dimension — that covers raw access.
            if sem not in catalog.dimensions:
                catalog.measures[sem] = Member(
                    name=sem, kind="measure", type="number",
                    title=col.display_name,
                    column=col.name, semantic_column=sem, agg=None,
                    row_level=True,
                )
            for suffix, agg in _COL_MEASURE_SUFFIXES.items():
                name = f"{sem}_{suffix}"
                catalog.measures[name] = Member(
                    name=name, kind="measure", type="number",
                    title=f"{col.display_name} ({agg.upper()})",
                    column=col.name, semantic_column=sem, agg=agg.upper(),
                )

    catalog.measures["row_count"] = Member(
        name="row_count", kind="measure", type="number", title="Row Count", agg="COUNT",
    )

    for metric in metrics:
        catalog.measures[metric.name] = Member(
            name=metric.name, kind="computed", type="number",
            title=metric.display_name, expression=metric.expression,
            format=metric.format, description=metric.description,
            row_level=expression_is_row_level(metric.expression),
        )

    return catalog


async def get_catalog(db: AsyncSession, dataset: Dataset) -> MemberCatalog:
    cols_result = await db.execute(
        select(DatasetColumn)
        .where(DatasetColumn.dataset_id == dataset.id)
        .order_by(DatasetColumn.position)
    )
    metrics_result = await db.execute(
        select(SemanticMetric).where(SemanticMetric.dataset_id == dataset.id)
    )
    return build_catalog(
        dataset,
        list(cols_result.scalars().all()),
        list(metrics_result.scalars().all()),
    )


def resolve_cube_query(query, catalog: MemberCatalog) -> dict[str, Any]:
    """
    Validate a SemanticQuery against the catalog and produce a Cube REST
    query dict. Raises UnknownMemberError for anything not in the catalog.
    """
    cube = catalog.cube_name

    if getattr(query, "mode", "auto") == "ohlc":
        raise UnknownMemberError("OHLC queries require the local engine")

    measures = []
    for m in query.measures:
        member = catalog.get(m)
        if member.kind == "dimension":
            raise UnknownMemberError(f"{m!r} is a dimension, not a measure")
        if member.row_level:
            raise UnknownMemberError(f"{m!r} is a raw/row-level member — it requires the local engine")
        measures.append(f"{cube}.{m}")

    dimensions = []
    for d in query.dimensions:
        member = catalog.get(d)
        if member.kind != "dimension":
            raise UnknownMemberError(f"{d!r} is not a dimension")
        dimensions.append(f"{cube}.{d}")

    cube_query: dict[str, Any] = {
        "measures": measures,
        "dimensions": dimensions,
        "limit": max(1, min(int(query.limit or 500), 5000)),
    }

    if query.time_dimension:
        member = catalog.get(query.time_dimension)
        if member.type != "time":
            raise UnknownMemberError(f"{query.time_dimension!r} is not a time dimension")
        td: dict[str, Any] = {"dimension": f"{cube}.{query.time_dimension}"}
        if query.granularity:
            td["granularity"] = query.granularity
        if query.date_range:
            td["dateRange"] = query.date_range
        cube_query["timeDimensions"] = [td]

    filters = []
    for f in query.filters:
        catalog.get(f.member)  # validates
        entry: dict[str, Any] = {"member": f"{cube}.{f.member}", "operator": f.operator}
        if f.operator not in ("set", "notSet"):
            entry["values"] = [str(v) for v in f.values]
        filters.append(entry)
    if filters:
        cube_query["filters"] = filters

    if query.order:
        order = []
        for m, direction in query.order.items():
            catalog.get(m)
            order.append([f"{cube}.{m}", direction])
        cube_query["order"] = order

    return cube_query


def normalize_cube_rows(rows: list[dict], catalog: MemberCatalog) -> list[dict]:
    """
    Strip the cube prefix from result keys:
      "ds_ab12cd34.spend_sum"  -> "spend_sum"
      "ds_ab12cd34.date.day"   -> "date"
    When both "date" and "date.day" appear, the granularity key wins.
    """
    prefix = f"{catalog.cube_name}."
    normalized = []
    for row in rows:
        out: dict[str, Any] = {}
        for key, value in row.items():
            name = key[len(prefix):] if key.startswith(prefix) else key
            parts = name.split(".")
            if len(parts) == 2 and parts[1] in ("day", "week", "month"):
                out[parts[0]] = value
            elif parts[0] not in out:
                out[parts[0]] = value
        normalized.append(out)
    return normalized


# ─── Cube schema version (recompilation trigger) ────────────────────────────


async def get_schema_version() -> str:
    try:
        value = await get_redis().get(SCHEMA_VERSION_KEY)
        return str(value or 0)
    except Exception:
        return "0"


async def bump_schema_version() -> None:
    """
    Bump whenever the semantic model changes (dataset READY, column flags,
    computed metrics). Cube polls this via schemaVersion and recompiles.
    A warm-up /meta request pays the compile cost right away instead of on
    the user's next query.
    """
    try:
        version = await get_redis().incr(SCHEMA_VERSION_KEY)
        logger.info("Cube schema version bumped", version=version)
    except Exception as e:
        logger.warning("Could not bump schema version", error=str(e))
        return

    try:
        from app.modules.semantic.cube_client import warm_up
        await warm_up()
    except Exception:
        pass
