"""Formula AST: validation, compilation for both engines, evaluation."""
from __future__ import annotations

import pytest

from app.modules.semantic.formula import (
    MAX_NODES,
    FormulaError,
    compile_formula_sql,
    evaluate_formula,
    expression_is_row_level,
    formula_is_row_level,
    iter_formula_columns,
    validate_formula,
)

# revenue - spend  (all raw terms → row-level)
ROW_LEVEL = {
    "type": "binary", "op": "-",
    "left": {"type": "agg", "agg": "none", "column": "revenue"},
    "right": {"type": "agg", "agg": "none", "column": "spend"},
}

# (SUM(revenue) − SUM(spend)) / SUM(spend) × 100
PROFIT_MARGIN = {
    "type": "binary", "op": "*",
    "left": {
        "type": "binary", "op": "/",
        "left": {
            "type": "binary", "op": "-",
            "left": {"type": "agg", "agg": "sum", "column": "revenue"},
            "right": {"type": "agg", "agg": "sum", "column": "spend"},
        },
        "right": {"type": "agg", "agg": "sum", "column": "spend"},
    },
    "right": {"type": "literal", "value": 100},
}


def quote(name: str) -> str:
    return f'"{name}"'


class TestCompile:
    def test_semantic_name_resolver(self):
        sql = compile_formula_sql(PROFIT_MARGIN, quote)
        assert sql == '(((SUM("revenue") - SUM("spend")) / NULLIF(SUM("spend"), 0)) * 100.0)'

    def test_original_name_resolver(self):
        mapping = {"revenue": "Revenue", "spend": "Ad Spend"}
        sql = compile_formula_sql(PROFIT_MARGIN, lambda c: quote(mapping[c]))
        assert '"Ad Spend"' in sql and '"Revenue"' in sql and "NULLIF" in sql

    def test_count_distinct(self):
        node = {"type": "agg", "agg": "count_distinct", "column": "campaign"}
        assert compile_formula_sql(node, quote) == 'COUNT(DISTINCT "campaign")'

    def test_ref_rejected_without_allow(self):
        with pytest.raises(FormulaError):
            compile_formula_sql({"type": "ref", "measure": "spend_sum"}, quote)

    def test_ref_resolved_with_allow(self):
        sql = compile_formula_sql(
            {"type": "ref", "measure": "spend_sum"}, quote,
            allow_refs=True, resolve_ref=quote,
        )
        assert sql == '"spend_sum"'


class TestValidate:
    def test_valid(self):
        validate_formula(PROFIT_MARGIN, {"revenue", "spend"})

    def test_unknown_column(self):
        with pytest.raises(FormulaError, match="Unknown column"):
            validate_formula(PROFIT_MARGIN, {"revenue"})

    def test_unknown_agg_rejected(self):
        with pytest.raises(FormulaError):
            validate_formula({"type": "agg", "agg": "median", "column": "spend"}, {"spend"})

    def test_malformed_node(self):
        with pytest.raises(FormulaError):
            validate_formula({"type": "banana"}, {"spend"})

    def test_literal_only_rejected(self):
        with pytest.raises(FormulaError, match="at least one column"):
            validate_formula({"type": "literal", "value": 5}, set())

    def test_size_cap(self):
        node: dict = {"type": "agg", "agg": "sum", "column": "spend"}
        for _ in range(MAX_NODES):
            node = {
                "type": "binary", "op": "+",
                "left": node, "right": {"type": "literal", "value": 1},
            }
        with pytest.raises(FormulaError, match="Formula too"):
            validate_formula(node, {"spend"})

    def test_ref_policy(self):
        node = {"type": "ref", "measure": "spend_sum"}
        with pytest.raises(FormulaError, match="not allowed"):
            validate_formula(node, set())
        validate_formula(node, set(), allow_refs=True, valid_refs={"spend_sum"})
        with pytest.raises(FormulaError, match="Unknown measure"):
            validate_formula(node, set(), allow_refs=True, valid_refs={"other"})


class TestEvaluate:
    def test_ref_formula(self):
        node = {
            "type": "binary", "op": "*",
            "left": {
                "type": "binary", "op": "/",
                "left": {
                    "type": "binary", "op": "-",
                    "left": {"type": "ref", "measure": "revenue_sum"},
                    "right": {"type": "ref", "measure": "spend_sum"},
                },
                "right": {"type": "ref", "measure": "spend_sum"},
            },
            "right": {"type": "literal", "value": 100},
        }
        assert evaluate_formula(node, {"revenue_sum": 400.0, "spend_sum": 100.0}) == 300.0

    def test_divide_by_zero_is_none(self):
        node = {
            "type": "binary", "op": "/",
            "left": {"type": "literal", "value": 1},
            "right": {"type": "ref", "measure": "spend"},
        }
        assert evaluate_formula(node, {"spend": 0}) is None

    def test_missing_ref_is_none(self):
        assert evaluate_formula({"type": "ref", "measure": "nope"}, {}) is None

    def test_agg_not_evaluable(self):
        with pytest.raises(FormulaError):
            evaluate_formula({"type": "agg", "agg": "sum", "column": "x"}, {})


def test_iter_columns():
    assert set(iter_formula_columns(PROFIT_MARGIN)) == {"revenue", "spend"}


class TestRawTerm:
    def test_none_compiles_to_bare_column(self):
        node = {"type": "agg", "agg": "none", "column": "spend"}
        assert compile_formula_sql(node, quote) == '"spend"'

    def test_row_level_expression_compiles(self):
        sql = compile_formula_sql(ROW_LEVEL, quote)
        assert sql == '("revenue" - "spend")'

    def test_row_level_detection(self):
        assert formula_is_row_level(ROW_LEVEL) is True
        assert formula_is_row_level(PROFIT_MARGIN) is False
        assert expression_is_row_level({"type": "formula", "root": ROW_LEVEL}) is True
        assert expression_is_row_level({"type": "formula", "root": PROFIT_MARGIN}) is False
        assert expression_is_row_level({"type": "ratio"}) is False
        assert expression_is_row_level(None) is False

    def test_pure_raw_formula_valid(self):
        validate_formula(ROW_LEVEL, {"revenue", "spend"})

    def test_mixing_raw_and_aggregate_rejected(self):
        mixed = {
            "type": "binary", "op": "-",
            "left": {"type": "agg", "agg": "sum", "column": "revenue"},
            "right": {"type": "agg", "agg": "none", "column": "spend"},
        }
        with pytest.raises(FormulaError, match="mix raw"):
            validate_formula(mixed, {"revenue", "spend"})

    def test_raw_with_literal_is_fine(self):
        node = {
            "type": "binary", "op": "*",
            "left": {"type": "agg", "agg": "none", "column": "spend"},
            "right": {"type": "literal", "value": 1.2},
        }
        validate_formula(node, {"spend"})
        assert formula_is_row_level(node) is True
