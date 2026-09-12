"""
seed.py — Seed initial admin + demo user accounts.
Run: docker compose exec backend python seed.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.core.settings import settings
from app.modules.auth.jwt import hash_password


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with SessionLocal() as db:
        from app.db.models import AdminUser, User

        # Seed admin
        admin_result = await db.execute(select(AdminUser).where(AdminUser.email == "admin@insightai.local"))
        if not admin_result.scalar_one_or_none():
            admin = AdminUser(
                email="admin@insightai.local",
                username="admin",
                hashed_password=hash_password("Admin@123456"),
                first_name="Platform",
                last_name="Admin",
                role="super_admin",
                is_active=True,
            )
            db.add(admin)
            print("Admin seeded: admin@insightai.local / Admin@123456")
        else:
            print("Admin already exists.")

        # Seed demo user
        user_result = await db.execute(select(User).where(User.email == "demo@insightai.local"))
        if not user_result.scalar_one_or_none():
            user = User(
                email="demo@insightai.local",
                hashed_password=hash_password("Demo@123456"),
                first_name="Demo",
                last_name="User",
                company="Acme Agency",
                is_active=True,
            )
            db.add(user)
            print("User seeded:  demo@insightai.local / Demo@123456")
        else:
            print("Demo user already exists.")

        await db.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
