"""create users table

Revision ID: 0001_create_users
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_create_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────
    # user_role_enum = postgresql.ENUM(
    #     "admin", "moderator", "user",
    #     name="user_role_enum",
    #     create_type=False,
    # )
    # user_status_enum = postgresql.ENUM(
    #     "active", "inactive", "banned",
    #     name="user_status_enum",
    #     create_type=False,
    # )
    # user_role_enum.create(op.get_bind(), checkfirst=True)
    # user_status_enum.create(op.get_bind(), checkfirst=True)

    # ── Table ────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email",           sa.String(255), nullable=False),
        sa.Column("username",        sa.String(50),  nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name",       sa.String(120), nullable=True),
        sa.Column("role",            sa.String(20),nullable=False,server_default="user"),
        sa.Column("status",          sa.String(20),nullable=False,server_default="active"),
        # sa.Column(
        #     "role",
        #     sa.Enum("admin", "moderator", "user", name="user_role_enum"),
        #     nullable=False,
        #     server_default="user",
        # ),
        # sa.Column(
        #     "status",
        #     sa.Enum("active", "inactive", "banned", name="user_status_enum"),
        #     nullable=False,
        #     server_default="active",
        # ),
        sa.Column("is_verified",  sa.Boolean(),                      nullable=False, server_default="false"),
        sa.Column("created_at",   sa.DateTime(timezone=True),        nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(timezone=True),        nullable=False, server_default=sa.text("now()")),
    )

    # ── Indexes ──────────────────────────────────────────────────────────
    op.create_index("ix_users_email",    "users", ["email"],    unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # ── updated_at trigger ───────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at;")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email",    table_name="users")
    op.drop_table("users")

    # op.execute("DROP TYPE IF EXISTS user_role_enum;")
    # op.execute("DROP TYPE IF EXISTS user_status_enum;")
