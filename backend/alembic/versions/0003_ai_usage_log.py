"""AI usage log: per-call token accounting for admin analytics.

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
        ),
        sa.Column("feature", sa.String(40), nullable=False, index=True),
        sa.Column("model", sa.String(120)),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_ai_usage_log_created_at", "ai_usage_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_log_created_at", table_name="ai_usage_log")
    op.drop_table("ai_usage_log")
