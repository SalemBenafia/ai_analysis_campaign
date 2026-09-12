"""Initial schema — all InsightAI tables.

Revision ID: 0001
"""
from __future__ import annotations

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("company", sa.String(200)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("preferences", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "admin_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, default="platform_admin"),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("principal_id", sa.String(100), nullable=False, index=True),
        sa.Column("principal_type", sa.String(50), nullable=False),
        sa.Column("jti", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("is_revoked", sa.Boolean, nullable=False, default=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("admin_id", UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("action", sa.String(200), nullable=False, index=True),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", sa.String(100)),
        sa.Column("details", sa.JSON),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_format", sa.String(20), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("minio_key", sa.String(500)),
        sa.Column("status", sa.String(30), nullable=False, default="uploading"),
        sa.Column("row_count", sa.Integer),
        sa.Column("column_count", sa.Integer),
        sa.Column("duckdb_table", sa.String(200)),
        sa.Column("error_message", sa.Text),
        sa.Column("meta", sa.JSON),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "dataset_columns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("col_type", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("is_metric", sa.Boolean, default=False),
        sa.Column("is_dimension", sa.Boolean, default=False),
        sa.Column("sample_values", sa.JSON),
        sa.Column("null_count", sa.Integer),
        sa.Column("unique_count", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_id", "name", name="uq_dataset_column_name"),
    )

    op.create_table(
        "dashboards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_default", sa.Boolean, default=False),
        sa.Column("layout", sa.JSON),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "dashboard_widgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("dashboard_id", UUID(as_uuid=True), sa.ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("viz_type", sa.String(30), nullable=False, default="bar"),
        sa.Column("echart_config", sa.JSON),
        sa.Column("query_sql", sa.Text),
        sa.Column("filters", sa.JSON),
        sa.Column("position", sa.JSON),
        sa.Column("refresh_interval", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "saved_insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("insight_type", sa.String(30), nullable=False, default="custom"),
        sa.Column("insight_definition", sa.JSON, nullable=False),
        sa.Column("echart_config", sa.JSON),
        sa.Column("ai_explanation", sa.Text),
        sa.Column("ai_recommendation", sa.Text),
        sa.Column("is_pinned", sa.Boolean, default=False),
        sa.Column("is_template", sa.Boolean, default=False),
        sa.Column("tags", sa.JSON),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "copilot_conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255)),
        sa.Column("context", sa.JSON),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "copilot_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("copilot_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("generated_sql", sa.Text),
        sa.Column("echart_config", sa.JSON),
        sa.Column("tool_calls", sa.JSON),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(30), nullable=False, default="generating"),
        sa.Column("minio_key", sa.String(500)),
        sa.Column("download_url", sa.String(500)),
        sa.Column("widget_ids", sa.JSON),
        sa.Column("meta", sa.JSON),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("is_deleted", sa.Boolean, nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "system_metric_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False, unique=True, index=True),
        sa.Column("total_users", sa.Integer, default=0),
        sa.Column("active_users", sa.Integer, default=0),
        sa.Column("new_users", sa.Integer, default=0),
        sa.Column("total_datasets", sa.Integer, default=0),
        sa.Column("total_queries", sa.Integer, default=0),
        sa.Column("total_reports", sa.Integer, default=0),
        sa.Column("avg_query_latency_ms", sa.Float),
        sa.Column("storage_bytes", sa.BigInteger),
        sa.Column("extra", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in [
        "system_metric_snapshots", "reports", "copilot_messages",
        "copilot_conversations", "saved_insights", "dashboard_widgets",
        "dashboards", "dataset_columns", "datasets", "audit_logs",
        "refresh_tokens", "admin_users", "users",
    ]:
        op.drop_table(table)
