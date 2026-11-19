from aiogram import Router

from bot.handlers import add_word, common, persona, review, settings, stickers, talk, words


def all_routers() -> list[Router]:
    # Order matters: persona's state handlers must see text before add_word,
    # and add_word goes last among content routers because it catches any free text.
    return [
        common.router,
        persona.router,
        review.router,
        words.router,
        settings.router,
        stickers.router,
        talk.router,
        add_word.router,
        common.fallback_router,
    ]
