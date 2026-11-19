import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.ai.service import build_ai
from bot.config import get_settings
from bot.db.session import make_engine, make_sessionmaker, run_migrations
from bot.handlers import all_routers
from bot.handlers.errors import on_error
from bot.images import arts, booru
from bot.jobs.scheduler import Scheduler
from bot.middlewares import DbMiddleware, OwnerOnlyMiddleware
from bot.persona.memory import ChatMemory

COMMANDS = [
    BotCommand(command="review", description="Повторить карточки"),
    BotCommand(command="list", description="Мои слова"),
    BotCommand(command="stats", description="Статистика"),
    BotCommand(command="persona", description="Персонаж"),
    BotCommand(command="practice", description="Разговорная практика вкл/выкл"),
    BotCommand(command="lang", description="Сменить язык"),
    BotCommand(command="delete", description="Удалить слово"),
    BotCommand(command="stickers", description="Стикеры персонажа"),
    BotCommand(command="remind", description="Напоминания"),
    BotCommand(command="memory", description="Что персонаж помнит обо мне"),
    BotCommand(command="backup", description="Бэкап базы сейчас"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    arts.STYLE = settings.reaction_style
    booru.configure(settings.danbooru_login, settings.danbooru_api_key)

    await run_migrations(settings.database_url)
    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(OwnerOnlyMiddleware(settings.owner_id))
    dp.update.outer_middleware(DbMiddleware(sessionmaker, settings))
    dp.include_routers(*all_routers())
    dp.errors.register(on_error)  # no silent failures: log + tell the user

    await bot.set_my_commands(COMMANDS)
    try:
        ai = build_ai(settings)
        scheduler = Scheduler(bot, sessionmaker, ai, settings)
        jobs = asyncio.create_task(scheduler.run())  # reminders, "I miss you", daily backup
        try:
            await dp.start_polling(bot, ai=ai, memory=ChatMemory(), scheduler=scheduler)
        finally:
            jobs.cancel()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped")
