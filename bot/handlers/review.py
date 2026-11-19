"""Flashcard review session: front → «show answer» → Again/Hard/Good/Easy → next card."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import srs, texts
from bot.db.models import Card, Deck, Persona, User
from bot.db.repo import Repo
from bot.langs import get_lang
from bot.images import arts
from bot.persona.card import PersonaCard, phrase
from bot.utils import esc, format_interval, utcnow

router = Router(name="review")

RATINGS = {1: ("🔁", "Снова"), 2: ("😬", "Трудно"), 3: ("👍", "Хорошо"), 4: ("😎", "Легко")}


def front_text(card: Card, deck: Deck, user: User) -> str:
    word = card.word
    if card.direction == "fwd":
        return f"{get_lang(deck.target_lang).flag} <b>{esc(word.display)}</b>\n\n<i>Как переводится?</i>"
    target = get_lang(deck.target_lang)
    return (
        f"{get_lang(user.native_lang).flag} <b>{esc('; '.join(word.translations))}</b>\n\n"
        f"<i>Как будет {target.adverb_ru}?</i>"
    )


async def send_next_card(
    message: Message,
    repo: Repo,
    user: User,
    deck: Deck,
    persona: PersonaCard,
    persona_row: Persona,
    just_reviewed: int | None = None,
) -> None:
    now = utcnow()
    card = await repo.next_due_card(deck.id, now, just_reviewed)
    if card is None:
        next_at = await repo.next_due_at(deck.id)
        if next_at is None:
            await message.answer("В колоде пока нет слов. Пришли мне слово — и начнём! ✨")
        else:
            done = phrase(persona, "review_done", ["На сейчас всё повторено! 🎉"])
            text = f"{esc(done)}\nСледующая карточка через {format_interval(next_at - now)}."
            if not await arts.send_reaction(message, repo, persona_row, persona, "review_done", text):
                await message.answer(text)
        return
    left = await repo.count_due(deck.id, now)
    header = f"<i>Осталось: {left}</i>\n\n" if left > 1 else ""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👀 Показать ответ", callback_data=f"show:{card.id}")]]
    )
    await message.answer(header + front_text(card, deck, user), reply_markup=keyboard)


@router.message(Command("review"))
async def cmd_review(
    message: Message,
    state: FSMContext,
    repo: Repo,
    user: User,
    deck: Deck,
    persona: PersonaCard,
    persona_row: Persona,
) -> None:
    await state.clear()
    await send_next_card(message, repo, user, deck, persona, persona_row)


@router.callback_query(F.data == "rv:start")
async def on_start_review(
    callback: CallbackQuery,
    state: FSMContext,
    repo: Repo,
    user: User,
    deck: Deck,
    persona: PersonaCard,
    persona_row: Persona,
) -> None:
    """«📚 Начать повторение» under a reminder."""
    await callback.answer()
    if isinstance(callback.message, Message):
        await state.clear()
        await callback.message.edit_reply_markup(reply_markup=None)
        await send_next_card(callback.message, repo, user, deck, persona, persona_row)


@router.callback_query(F.data.startswith("show:"))
async def on_show(callback: CallbackQuery, repo: Repo, user: User, deck: Deck) -> None:
    card = await repo.get_card(int((callback.data or "").split(":")[1]))
    message = callback.message
    if card is None or not isinstance(message, Message):
        await callback.answer(texts.STALE)
        return
    await callback.answer()
    intervals = srs.preview(card.fsrs, utcnow())
    buttons = [
        InlineKeyboardButton(
            text=f"{emoji} {label} · {format_interval(intervals[rating])}",
            callback_data=f"rate:{card.id}:{rating}",
        )
        for rating, (emoji, label) in RATINGS.items()
    ]
    await message.edit_text(
        front_text(card, deck, user) + "\n\n━━━━━━━━━━\n" + texts.render_word(texts.word_to_dict(card.word)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:]]),
    )


@router.callback_query(F.data.startswith("rate:"))
async def on_rate(
    callback: CallbackQuery, repo: Repo, user: User, deck: Deck, persona: PersonaCard, persona_row: Persona
) -> None:
    _, card_id, rating_str = (callback.data or "").split(":")
    card = await repo.get_card(int(card_id))
    message = callback.message
    if card is None or not isinstance(message, Message):
        await callback.answer(texts.STALE)
        return
    last = await repo.last_review_at(card.id)
    if last is not None and last >= message.date:
        await callback.answer("Уже оценено 🙂")
        return
    await callback.answer()

    rating = int(rating_str)
    now = utcnow()
    new_state, due = srs.review(card.fsrs, rating, now)
    await repo.record_review(card, rating, new_state, due, now)

    emoji, label = RATINGS[rating]
    if rating == 1:
        reaction = phrase(persona, "wrong", ["Ничего, повторим! 💪"])
    else:
        reaction = phrase(persona, "correct", ["Отлично! ✨"])
    await message.edit_text(
        message.html_text
        + f"\n\n{emoji} {label} · следующий раз через {format_interval(due - now)}\n<i>{esc(reaction)}</i>"
    )
    await arts.send_reaction(message, repo, persona_row, persona, "wrong" if rating == 1 else "correct")
    await send_next_card(message, repo, user, deck, persona, persona_row, just_reviewed=card.id)
