"""add audit_logs table

Revision ID: 0002_add_audit_logs
Revises: 0001_create_users
Create Date: 2026-01-02 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0002_add_audit_logs"
down_revision = "0001_create_users"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("actor_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(64),                 nullable=False),
        sa.Column("target_id",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", sa.String(45),                 nullable=True),
        sa.Column("user_agent", sa.Text(),                     nullable=True),
        sa.Column("metadata",   postgresql.JSONB(),            nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_audit_logs_actor_id",   "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_target_id",  "audit_logs", ["target_id"])
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_target_id",  table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id",   table_name="audit_logs")
    op.drop_table("audit_logs")
