import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from bot.db.models import Base


def make_engine(url: str) -> AsyncEngine:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        folder = os.path.dirname(parsed.database)
        if folder:
            os.makedirs(folder, exist_ok=True)
    return create_async_engine(url)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables directly (tests only; the bot uses Alembic migrations)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


async def run_migrations(url: str) -> None:
    """alembic upgrade head. Runs in a thread because Alembic's async env starts its own event loop."""
    make_engine(url)  # creates the SQLite folder if needed
    await asyncio.to_thread(command.upgrade, alembic_config(url), "head")
