"""
Admin seeder — run once to bootstrap the first superadmin.

Usage:
    python -m scripts.seed_admin \
        --email admin@example.com \
        --username admin \
        --password "Admin1234!" \
        --full-name "System Admin"

The script is idempotent: if the email already exists it prints a notice
and exits without modifying the existing record.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# Ensure project root is on the path when run as a module
sys.path.insert(0, ".")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.domain.entities.user import User, UserRole, UserStatus
from app.infrastructure.database.models import Base
from app.infrastructure.database.user_repository import SQLUserRepository
from app.infrastructure.security.password import hash_password


async def seed(
    email: str,
    username: str,
    password: str,
    full_name: str | None,
) -> None:
    engine = create_async_engine(settings.database_url, echo=False)

    # Ensure tables exist (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        repo = SQLUserRepository(session)

        if await repo.exists_by_email(email):
            print(f"[seed] Admin '{email}' already exists — skipping.")
            await engine.dispose()
            return

        admin = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            is_verified=True,
        )
        created = await repo.create(admin)
        await session.commit()
        print(f"[seed] Admin created → id={created.id}  email={created.email}")

    await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the first admin user.")
    parser.add_argument("--email",     required=True)
    parser.add_argument("--username",  required=True)
    parser.add_argument("--password",  required=True)
    parser.add_argument("--full-name", default=None, dest="full_name")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    print(f"[seed] Starting admin seeding with email='{args.email}' username='{args.username}'")
    asyncio.run(seed(args.email, args.username, args.password, args.full_name))
