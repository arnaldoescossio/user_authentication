from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.entities.user import UserRole, UserStatus


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


class UserORM(Base):
    """
    SQLAlchemy 2.0 ORM model using Mapped[] typed columns.
    Mapped to the 'users' table in PostgreSQL.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    role: Mapped[UserRole] = mapped_column(
        # Enum(UserRole, name="user_role_enum", create_type=True),
        String(20),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER,
    )
    status: Mapped[UserStatus] = mapped_column(
        # Enum(UserStatus, name="user_status_enum", create_type=True),
        String(20),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<UserORM id={self.id} email={self.email} role={self.role}>"
