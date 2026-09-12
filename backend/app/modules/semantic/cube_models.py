"""
app/modules/semantic/cube_models.py
=====================================
Generates Cube YAML data models from dataset metadata. One cube per READY
dataset, reading its marts parquet from MinIO via DuckDB httpfs.

Served to the Cube container by internal_router (repositoryFactory fetches
it at schema-compile time), so Postgres stays the single source of truth.
"""
from __future__ import annotations

import yaml

from app.core.settings import settings
from app.db.models import ColumnType, Dataset, DatasetColumn, SemanticMetric
from app.modules.semantic.formula import compile_formula_sql, expression_is_row_level
from app.modules.semantic.registry import cube_name_for

_CUBE_DIM_TYPE = {
    ColumnType.TEXT: "string",
    ColumnType.DATE: "time",
    ColumnType.DATETIME: "time",
    ColumnType.BOOLEAN: "boolean",
    ColumnType.INTEGER: "number",
    ColumnType.FLOAT: "number",
}


def compile_expression_sql(expression: dict) -> str:
    """
    Compile a structured metric expression to SQL over the marts parquet
    (semantic snake_case column names). Only structured shapes are accepted —
    never raw user SQL.

    {"type": "ratio",
     "numerator":   {"agg": "sum", "column": "revenue"},
     "denominator": {"agg": "sum", "column": "spend"},
     "multiplier": 1}

    {"type": "formula", "root": <recursive node — see semantic/formula.py>}
    """
    kind = expression.get("type")
    if kind == "ratio":
        num = expression["numerator"]
        den = expression["denominator"]
        multiplier = expression.get("multiplier", 1)
        num_sql = f"{_agg(num)}({_col(num)})"
        den_sql = f"{_agg(den)}({_col(den)})"
        if multiplier and multiplier != 1:
            num_sql = f"{num_sql} * {float(multiplier)}"
        return f"({num_sql}) / NULLIF({den_sql}, 0)"
    if kind == "aggregate":
        return f"{_agg(expression)}({_col(expression)})"
    if kind == "formula":
        return compile_formula_sql(
            expression.get("root") or {},
            lambda column: _col({"column": column}),
        )
    raise ValueError(f"Unsupported expression type: {kind!r}")


_ALLOWED_AGGS = {"sum", "avg", "min", "max", "count"}


def _agg(part: dict) -> str:
    agg = str(part.get("agg", "sum")).lower()
    if agg not in _ALLOWED_AGGS:
        raise ValueError(f"Aggregation not allowed in metric expression: {agg!r}")
    return agg.upper()


def _col(part: dict) -> str:
    col = str(part.get("column", ""))
    if not col.replace("_", "").isalnum() or not col[:1].isalpha():
        raise ValueError(f"Invalid column in metric expression: {col!r}")
    return f'"{col}"'


def build_cube_for_dataset(
    dataset: Dataset,
    columns: list[DatasetColumn],
    metrics: list[SemanticMetric],
) -> dict:
    s3_path = f"s3://{settings.MINIO_BUCKET_DATASETS}/{dataset.marts_key}"

    dimensions = []
    measures = [{"name": "row_count", "type": "count"}]

    for col in columns:
        sem = col.semantic_name or col.name
        if col.is_dimension:
            dimensions.append({
                "name": sem,
                "sql": sem,
                "type": _CUBE_DIM_TYPE.get(col.col_type, "string"),
                "title": col.display_name,
            })
        if col.is_metric:
            for agg in ("sum", "avg", "min", "max"):
                measures.append({
                    "name": f"{sem}_{agg}",
                    "sql": sem,
                    "type": agg,
                    "title": f"{col.display_name} ({agg.upper()})",
                })

    for metric in metrics:
        # Row-level formula metrics (raw column values) can't be Cube measures —
        # they run on the DuckDB detail path, like raw column measures.
        if expression_is_row_level(metric.expression):
            continue
        measures.append({
            "name": metric.name,
            "type": "number",
            "sql": compile_expression_sql(metric.expression),
            "title": metric.display_name,
            **({"description": metric.description} if metric.description else {}),
        })

    return {
        "name": cube_name_for(dataset),
        "sql": f"SELECT * FROM read_parquet('{s3_path}')",
        "dimensions": dimensions,
        "measures": measures,
    }


def build_models_yaml(
    datasets: list[tuple[Dataset, list[DatasetColumn], list[SemanticMetric]]],
) -> str:
    """One YAML document containing every READY dataset's cube."""
    cubes = [
        build_cube_for_dataset(ds, cols, mets)
        for ds, cols, mets in datasets
        if ds.marts_key
    ]
    return yaml.safe_dump({"cubes": cubes}, sort_keys=False, allow_unicode=True)
