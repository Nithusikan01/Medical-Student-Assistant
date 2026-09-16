"""telemetry traces and spans

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-16 23:58:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_traces",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="ok",
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=True),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ok', 'error')",
            name=op.f("ck_rag_traces_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rag_traces")),
    )
    op.create_index("ix_rag_traces_started_at", "rag_traces", ["started_at"])
    op.create_index(
        "ix_rag_traces_status_started_at",
        "rag_traces",
        ["status", "started_at"],
    )
    op.create_index(
        "ix_rag_traces_conversation_id",
        "rag_traces",
        ["conversation_id"],
    )
    op.create_index("ix_rag_traces_user_id", "rag_traces", ["user_id"])

    op.create_table(
        "rag_spans",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("parent_span_id", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="ok",
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ok', 'error')",
            name=op.f("ck_rag_spans_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rag_spans")),
    )
    op.create_index(
        "ix_rag_spans_trace_id_started_at",
        "rag_spans",
        ["trace_id", "started_at"],
    )
    op.create_index(
        "ix_rag_spans_stage_started_at",
        "rag_spans",
        ["stage", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_spans_stage_started_at", table_name="rag_spans")
    op.drop_index("ix_rag_spans_trace_id_started_at", table_name="rag_spans")
    op.drop_table("rag_spans")

    op.drop_index("ix_rag_traces_user_id", table_name="rag_traces")
    op.drop_index("ix_rag_traces_conversation_id", table_name="rag_traces")
    op.drop_index("ix_rag_traces_status_started_at", table_name="rag_traces")
    op.drop_index("ix_rag_traces_started_at", table_name="rag_traces")
    op.drop_table("rag_traces")
