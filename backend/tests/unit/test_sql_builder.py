"""Injection corpus + identifier validation for the safe SQL builder."""
from __future__ import annotations

import pytest

from app.modules.analytics.sql_builder import (
    UnsafeIdentifierError,
    UnsafeSQLError,
    compile_filters,
    quote_ident,
    validate_agg,
    validate_select,
)

ALLOWED = {"spend", "revenue", "campaign", "date"}
TABLE = "ds_test_12345678"


class TestQuoteIdent:
    def test_known_column_is_quoted(self):
        assert quote_ident("spend", ALLOWED) == '"spend"'

    @pytest.mark.parametrize("bad", [
        'spend"; DROP TABLE users; --',
        "spend' OR 1=1 --",
        "other_column",
        "",
        "spend); ATTACH ':memory:' AS x; --",
    ])
    def test_unknown_or_hostile_identifier_rejected(self, bad):
        with pytest.raises(UnsafeIdentifierError):
            quote_ident(bad, ALLOWED)


class TestCompileFilters:
    def test_values_become_parameters(self):
        where, params = compile_filters(
            [{"field": "spend", "operator": ">", "value": 500}], ALLOWED
        )
        assert where == 'WHERE "spend" > ?'
        assert params == [500]

    def test_semantic_shape_supported(self):
        where, params = compile_filters(
            [{"member": "revenue", "operator": "gte", "values": [100]}], ALLOWED
        )
        assert where == 'WHERE "revenue" >= ?'
        assert params == [100]

    def test_hostile_value_stays_a_parameter(self):
        where, params = compile_filters(
            [{"field": "campaign", "operator": "=", "value": "x'; DROP TABLE users; --"}],
            ALLOWED,
        )
        assert "DROP" not in where
        assert params == ["x'; DROP TABLE users; --"]

    def test_unknown_operator_rejected(self):
        with pytest.raises(UnsafeSQLError):
            compile_filters([{"field": "spend", "operator": "LIKE OR 1=1", "value": 1}], ALLOWED)

    def test_unknown_field_rejected(self):
        with pytest.raises(UnsafeIdentifierError):
            compile_filters([{"field": "nope", "operator": "=", "value": 1}], ALLOWED)


class TestValidateAgg:
    def test_allowlisted(self):
        assert validate_agg("sum") == "SUM"

    def test_rejected(self):
        with pytest.raises(UnsafeSQLError):
            validate_agg("SUM(1)); DROP TABLE x; --")


class TestValidateSelect:
    def test_plain_select_ok(self):
        validate_select(f"SELECT campaign, SUM(spend) FROM {TABLE} GROUP BY 1", TABLE)

    def test_cte_over_own_table_ok(self):
        validate_select(
            f"WITH t AS (SELECT * FROM {TABLE}) SELECT * FROM t LIMIT 5", TABLE
        )

    @pytest.mark.parametrize("sql", [
        "DROP TABLE ds_test_12345678",
        "SELECT 1; DROP TABLE ds_test_12345678",
        "INSERT INTO ds_test_12345678 VALUES (1)",
        "SELECT * FROM ds_other_users_table",
        "SELECT * FROM ds_test_12345678 JOIN ds_other_table USING (id)",
        "SELECT * FROM (SELECT * FROM ds_other_table) q",
        "PRAGMA database_list",
        "ATTACH 'other.db' AS other",
    ])
    def test_hostile_sql_rejected(self, sql):
        with pytest.raises(UnsafeSQLError):
            validate_select(sql, TABLE)
