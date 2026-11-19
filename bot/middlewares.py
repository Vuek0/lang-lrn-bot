from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repo
from bot.persona.card import PersonaCard
from bot.persona.memory import ChatMemory
from bot.utils import utcnow

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class OwnerOnlyMiddleware(BaseMiddleware):
    """Personal bot: silently ignore everyone except the owner."""

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id != self.owner_id:
            return None
        return await handler(event, data)


CHAT_HISTORY = 12  # messages of recent conversation the persona sees


async def _remember_activity(repo: Repo, memory: ChatMemory, user: User) -> None:
    """Keep when the user was last active (mood, "I miss you" reminders) and restore the chat after restarts."""
    memory.set_previous_active(user.id, user.last_active_at)
    user.last_active_at = utcnow()
    if memory.needs_loading(user.id):
        memory.load(user.id, await repo.recent_chat(user.id, CHAT_HISTORY))


class DbMiddleware(BaseMiddleware):
    """One DB session per update; injects repo, user and active deck into handlers."""

    def __init__(self, sessionmaker: async_sessionmaker, settings: Settings):
        self.sessionmaker = sessionmaker
        self.settings = settings

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self.sessionmaker() as session:
            repo = Repo(session)
            data["repo"] = repo
            if tg_user := data.get("event_from_user"):
                data["user"], data["deck"] = await repo.ensure_user(
                    tg_user.id,
                    native_lang=self.settings.native_lang,
                    timezone=self.settings.timezone,
                    target_lang=self.settings.default_target_lang,
                )
                data["persona_row"] = await repo.active_persona(data["user"])
                data["persona"] = PersonaCard.model_validate(data["persona_row"].card)
                if (memory := data.get("memory")) is not None:
                    await _remember_activity(repo, memory, data["user"])
            result = await handler(event, data)
            await session.commit()
            return result
