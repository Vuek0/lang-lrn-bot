"""The main menu: a persistent keyboard under the input field, so commands are one tap away."""

from aiogram import F
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

REVIEW = "📚 Повторить"
WORDS = "📋 Мои слова"
STATS = "📊 Статистика"
PERSONA = "🎭 Персонаж"
PRACTICE = "🗣 Практика"
MORE = "⚙️ Ещё"

BUTTONS = (REVIEW, WORDS, STATS, PERSONA, PRACTICE, MORE)

# Text handlers waiting for free input (a word, a translation, a persona request) must not take these
NOT_MENU = ~F.text.in_(set(BUTTONS))

MORE_TEXT = (
    "⚙️ <b>Ещё команды</b> — нажми на нужную:\n\n"
    "/stickers — какие стикеры присылает персонаж\n"
    "/remind — напоминания\n"
    "/memory — что персонаж помнит о тебе\n"
    "/lang — сменить язык\n"
    "/backup — бэкап базы сейчас\n"
    "/delete <i>слово</i> — удалить слово\n"
    "/help — помощь"
)


def main_keyboard() -> ReplyKeyboardMarkup:
    rows = [BUTTONS[i : i + 2] for i in range(0, len(BUTTONS), 2)]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Слово, вопрос или голосовое…",
    )
