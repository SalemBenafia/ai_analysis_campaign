"""Semantic layer: parquet keys, semantic names, computed metrics,
report schedules, live widget queries, copilot semantic queries.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── datasets: parquet locations for the Cube/dbt pipeline ────────────────
    op.add_column("datasets", sa.Column("parquet_key", sa.String(500)))
    op.add_column("datasets", sa.Column("marts_key", sa.String(500)))

    # ── dataset_columns: snake_case name used in marts parquet / Cube ────────
    op.add_column("dataset_columns", sa.Column("semantic_name", sa.String(255)))

    # ── semantic_metrics: computed metrics (ROAS, CTR, custom ratios) ────────
    op.create_table(
        "semantic_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "dataset_id", UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("expression", sa.JSON, nullable=False),
        sa.Column("format", sa.String(20)),
        sa.Column("is_auto", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_id", "name", name="uq_semantic_metric_name"),
    )

    # ── report_schedules ──────────────────────────────────────────────────────
    op.create_table(
        "report_schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "owner_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column(
            "dataset_id", UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("cadence", sa.String(10), nullable=False, server_default="weekly"),
        sa.Column("hour_utc", sa.Integer, nullable=False, server_default="6"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── dashboard_widgets: live semantic source + insight link ───────────────
    op.add_column(
        "dashboard_widgets",
        sa.Column(
            "insight_id", UUID(as_uuid=True),
            sa.ForeignKey("saved_insights.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.add_column("dashboard_widgets", sa.Column("semantic_query", sa.JSON))

    # ── copilot_messages: semantic query behind an AI answer ─────────────────
    op.add_column("copilot_messages", sa.Column("semantic_query", sa.JSON))


def downgrade() -> None:
    op.drop_column("copilot_messages", "semantic_query")
    op.drop_column("dashboard_widgets", "semantic_query")
    op.drop_column("dashboard_widgets", "insight_id")
    op.drop_table("report_schedules")
    op.drop_table("semantic_metrics")
    op.drop_column("dataset_columns", "semantic_name")
    op.drop_column("datasets", "marts_key")
    op.drop_column("datasets", "parquet_key")
