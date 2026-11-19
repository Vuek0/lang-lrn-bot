from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.db.models import Deck, Persona, User
from bot.images.arts import answer_with_avatar
from bot.db.repo import Repo
from bot.langs import LANGS, get_lang
from bot.persona.card import PersonaCard, phrase
from bot import menu

router = Router(name="common")
fallback_router = Router(name="fallback")


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(
    message: Message, state: FSMContext, repo: Repo, deck: Deck, persona: PersonaCard, persona_row: Persona
) -> None:
    await state.clear()
    greeting = phrase(persona, "greeting", ["Привет! 👋"])
    await answer_with_avatar(
        message, repo, persona_row, texts.help_text(get_lang(deck.target_lang), greeting),
        reply_markup=menu.main_keyboard(),
    )


@router.message(F.text == menu.MORE)
async def on_more(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(menu.MORE_TEXT, reply_markup=menu.main_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Окей, отменила 🙂")


def _langs_keyboard(native: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=f"{lang.flag} {lang.name_ru}", callback_data=f"lang:{lang.code}")
        for lang in LANGS.values()
        if lang.code != native
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i : i + 2] for i in range(0, len(buttons), 2)])


@router.message(Command("lang"))
async def cmd_lang(message: Message, command: CommandObject, state: FSMContext, repo: Repo, user: User) -> None:
    await state.clear()
    code = (command.args or "").strip().lower()
    if code:
        await _switch(message, repo, user, code)
        return
    await message.answer("Какой язык учим? 🌍", reply_markup=_langs_keyboard(user.native_lang))


@router.callback_query(F.data.startswith("lang:"))
async def on_lang(callback: CallbackQuery, repo: Repo, user: User) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await _switch(callback.message, repo, user, callback.data.split(":", 1)[1])


async def _switch(message: Message, repo: Repo, user: User, code: str) -> None:
    if code not in LANGS or code == user.native_lang:
        await message.answer("Такого языка я пока не знаю 🤔 Выбери из списка: /lang")
        return
    deck = await repo.switch_language(user, code)
    lang = get_lang(code)
    count = await repo.count_words(deck.id)
    await message.answer(f"Переключилась на {lang.flag} <b>{lang.name_ru}</b>! Слов в колоде: {count}")


@fallback_router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    await callback.answer(texts.STALE)


@fallback_router.message()
async def unknown_message(message: Message) -> None:
    if message.text and message.text.startswith("/"):
        await message.answer("Не знаю такой команды 🤔 /help")
    else:
        await message.answer("Я пока понимаю только текст и голосовые 🙂 /help")
