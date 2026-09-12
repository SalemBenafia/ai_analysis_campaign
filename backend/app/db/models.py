"""
app/db/models.py
=================
All SQLAlchemy ORM models for InsightAI.

Domain overview:

  User (media buyer) ──┬─< Dataset >──< DatasetColumn
                        │       │
                        │       └─< CopilotConversation >──< CopilotMessage
                        │
                        ├─< Dashboard >──< DashboardWidget
                        │
                        ├─< SavedInsight
                        │
                        ├─< Report >──< ReportSchedule
                        │
                        └── RefreshToken

  AdminUser ───────────┬── AuditLog
                        └── SystemMetricSnapshot

Three actors: User (media buyer), Admin, AI Agent System.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.common.models import BaseModel, SoftDeleteModel


# ─── Enums ──────────────────────────────────────────────────────────────────────

class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    PLATFORM_ADMIN = "platform_admin"
    ANALYST = "analyst"


class DatasetStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class ColumnType(str, enum.Enum):
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"


class InsightType(str, enum.Enum):
    AI_GENERATED = "ai_generated"
    CUSTOM = "custom"
    TEMPLATE = "template"


class VisualizationType(str, enum.Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    TABLE = "table"
    KPI = "kpi"
    AREA = "area"
    HEATMAP = "heatmap"
    CANDLESTICK = "candlestick"


class ReportStatus(str, enum.Enum):
    GENERATING = "generating"
    READY = "ready"
    ERROR = "error"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ─── Users ──────────────────────────────────────────────────────────────────────

class User(SoftDeleteModel):
    """Media buyer / agency analyst — primary platform user."""
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(200))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    preferences: Mapped[Optional[dict]] = mapped_column(
        JSON, default={"theme": "dark", "default_date_range": "last_30_days"}
    )

    datasets: Mapped[list["Dataset"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    dashboards: Mapped[list["Dashboard"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    saved_insights: Mapped[list["SavedInsight"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    conversations: Mapped[list["CopilotConversation"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AdminUser(SoftDeleteModel):
    """Platform administrator."""
    __tablename__ = "admin_users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole, native_enum=False), default=AdminRole.PLATFORM_ADMIN, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="admin")


class RefreshToken(BaseModel):
    """Stored refresh token for rotation — revoked on use."""
    __tablename__ = "refresh_tokens"

    principal_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "user" | "admin"
    jti: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(BaseModel):
    """Admin action audit trail."""
    __tablename__ = "audit_logs"

    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100))
    resource_id: Mapped[Optional[str]] = mapped_column(String(100))
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    admin: Mapped[Optional["AdminUser"]] = relationship(back_populates="audit_logs")


# ─── Data Layer ─────────────────────────────────────────────────────────────────

class Dataset(SoftDeleteModel):
    """
    A data file uploaded by the user (CSV, Excel, JSON, Parquet).
    Schema is inferred dynamically — no hard validation on columns.
    Raw data is stored in DuckDB; this table is the metadata record.
    """
    __tablename__ = "datasets"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)  # csv | xlsx | json | parquet
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    minio_key: Mapped[Optional[str]] = mapped_column(String(500))  # object storage path
    status: Mapped[DatasetStatus] = mapped_column(
        Enum(DatasetStatus, native_enum=False), default=DatasetStatus.UPLOADING, nullable=False, index=True
    )
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    column_count: Mapped[Optional[int]] = mapped_column(Integer)
    duckdb_table: Mapped[Optional[str]] = mapped_column(String(200))  # DuckDB table name
    parquet_key: Mapped[Optional[str]] = mapped_column(String(500))  # processed parquet (MinIO)
    marts_key: Mapped[Optional[str]] = mapped_column(String(500))    # dbt/polars marts parquet (MinIO) — read by Cube
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, default={})  # extra metadata

    owner: Mapped["User"] = relationship(back_populates="datasets")
    columns: Mapped[list["DatasetColumn"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetColumn.position"
    )
    saved_insights: Mapped[list["SavedInsight"]] = relationship(back_populates="dataset")
    conversations: Mapped[list["CopilotConversation"]] = relationship(back_populates="dataset")


class DatasetColumn(BaseModel):
    """Inferred schema column for a dataset."""
    __tablename__ = "dataset_columns"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    semantic_name: Mapped[Optional[str]] = mapped_column(String(255))  # snake_case name in marts parquet / Cube
    col_type: Mapped[ColumnType] = mapped_column(Enum(ColumnType, native_enum=False), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_metric: Mapped[bool] = mapped_column(Boolean, default=False)   # numeric → metric
    is_dimension: Mapped[bool] = mapped_column(Boolean, default=False)  # categorical → dimension
    sample_values: Mapped[Optional[list]] = mapped_column(JSON, default=[])
    null_count: Mapped[Optional[int]] = mapped_column(Integer)
    unique_count: Mapped[Optional[int]] = mapped_column(Integer)

    dataset: Mapped["Dataset"] = relationship(back_populates="columns")

    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uq_dataset_column_name"),
    )


class SemanticMetric(BaseModel):
    """
    A computed metric in the semantic layer (Cube measure of type `number`).

    expression shape (structured — compiled to SQL by the semantic module,
    never raw SQL from the user):
    {
      "type": "ratio",
      "numerator":   {"agg": "sum", "column": "revenue"},
      "denominator": {"agg": "sum", "column": "spend"},
      "multiplier": 1
    }
    """
    __tablename__ = "semantic_metrics"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # snake_case member name (e.g. "roas")
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    expression: Mapped[dict] = mapped_column(JSON, nullable=False)
    format: Mapped[Optional[str]] = mapped_column(String(20))  # number | percent | currency
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)  # auto-detected (ROAS/CTR/...)

    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uq_semantic_metric_name"),
    )


# ─── Dashboard Layer ─────────────────────────────────────────────────────────────

class Dashboard(SoftDeleteModel):
    """Custom dashboard with draggable ECharts widgets."""
    __tablename__ = "dashboards"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    layout: Mapped[Optional[dict]] = mapped_column(JSON, default={"cols": 12, "rows": []})

    owner: Mapped["User"] = relationship(back_populates="dashboards")
    widgets: Mapped[list["DashboardWidget"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan"
    )


class DashboardWidget(BaseModel):
    """
    A single chart/KPI widget on a dashboard.
    echart_config stores the full ECharts option JSON.
    query stores the DuckDB SQL or insight definition.
    """
    __tablename__ = "dashboard_widgets"

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    insight_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_insights.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    viz_type: Mapped[VisualizationType] = mapped_column(
        Enum(VisualizationType, native_enum=False), default=VisualizationType.BAR, nullable=False
    )
    echart_config: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    query_sql: Mapped[Optional[str]] = mapped_column(Text)
    semantic_query: Mapped[Optional[dict]] = mapped_column(JSON)  # SemanticQuery JSON (live data source)
    filters: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    position: Mapped[dict] = mapped_column(JSON, default={"x": 0, "y": 0, "w": 6, "h": 4})
    refresh_interval: Mapped[Optional[int]] = mapped_column(Integer)  # seconds

    dashboard: Mapped["Dashboard"] = relationship(back_populates="widgets")


# ─── Insight Layer ───────────────────────────────────────────────────────────────

class SavedInsight(SoftDeleteModel):
    """
    A reusable insight object — can be AI-generated or manually built.

    insight_definition shape:
    {
      "metric": "ROAS",
      "dimension": "Campaign",
      "filters": [{"field": "Spend", "operator": ">", "value": 500}],
      "visualization": "BarChart",
      "date_range": "last_30_days"
    }
    """
    __tablename__ = "saved_insights"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    insight_type: Mapped[InsightType] = mapped_column(
        Enum(InsightType, native_enum=False), default=InsightType.CUSTOM, nullable=False
    )
    insight_definition: Mapped[dict] = mapped_column(JSON, nullable=False, default={})
    echart_config: Mapped[Optional[dict]] = mapped_column(JSON)  # cached chart config
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text)  # AI narrative
    ai_recommendation: Mapped[Optional[str]] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=[])

    owner: Mapped["User"] = relationship(back_populates="saved_insights")
    dataset: Mapped[Optional["Dataset"]] = relationship(back_populates="saved_insights")


# ─── AI Copilot Layer ────────────────────────────────────────────────────────────

class CopilotConversation(SoftDeleteModel):
    """A chat session between the user and the AI Copilot."""
    __tablename__ = "copilot_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255))
    context: Mapped[Optional[dict]] = mapped_column(JSON, default={})  # dataset schema summary

    user: Mapped["User"] = relationship(back_populates="conversations")
    dataset: Mapped[Optional["Dataset"]] = relationship(back_populates="conversations")
    messages: Mapped[list["CopilotMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="CopilotMessage.created_at"
    )


class CopilotMessage(BaseModel):
    """Single turn in a copilot conversation."""
    __tablename__ = "copilot_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("copilot_conversations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, native_enum=False), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[Optional[str]] = mapped_column(Text)  # SQL from NL→SQL tool
    semantic_query: Mapped[Optional[dict]] = mapped_column(JSON)  # last semantic query (for save-as-insight)
    echart_config: Mapped[Optional[dict]] = mapped_column(JSON)  # chart from viz tool
    tool_calls: Mapped[Optional[list]] = mapped_column(JSON, default=[])  # tool invocations log
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    conversation: Mapped["CopilotConversation"] = relationship(back_populates="messages")


class AIUsageLog(BaseModel):
    """One LLM interaction (copilot turn, NL-create, narration) — token accounting
    for the admin analytics page. Never blocks the feature that records it."""
    __tablename__ = "ai_usage_log"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    feature: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # copilot | nl_create | narrate
    model: Mapped[Optional[str]] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ─── Report Layer ────────────────────────────────────────────────────────────────

class Report(SoftDeleteModel):
    """AI-generated or manual PDF report."""
    __tablename__ = "reports"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, native_enum=False), default=ReportStatus.GENERATING, nullable=False
    )
    minio_key: Mapped[Optional[str]] = mapped_column(String(500))
    download_url: Mapped[Optional[str]] = mapped_column(String(500))
    widget_ids: Mapped[Optional[list]] = mapped_column(JSON, default=[])  # included widget UUIDs
    meta: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    owner: Mapped["User"] = relationship(back_populates="reports")


class ReportSchedule(BaseModel):
    """Recurring report generation (runs via the in-process scheduler)."""
    __tablename__ = "report_schedules"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cadence: Mapped[str] = mapped_column(String(10), nullable=False, default="weekly")  # daily | weekly
    hour_utc: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ─── System Monitoring ───────────────────────────────────────────────────────────

class SystemMetricSnapshot(BaseModel):
    """Nightly platform-level rollup for admin analytics."""
    __tablename__ = "system_metric_snapshots"

    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True, nullable=False, index=True)
    total_users: Mapped[int] = mapped_column(Integer, default=0)
    active_users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    total_datasets: Mapped[int] = mapped_column(Integer, default=0)
    total_queries: Mapped[int] = mapped_column(Integer, default=0)
    total_reports: Mapped[int] = mapped_column(Integer, default=0)
    avg_query_latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    storage_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, default={})
