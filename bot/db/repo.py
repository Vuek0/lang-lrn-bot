from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot import srs
from bot.db.models import Card, Deck, Persona, PersonaArt, ReviewLog, User, Word
from bot.langs import get_lang
from bot.persona.card import DEFAULT_CARD

# The reverse card (native → target) becomes due later, so you don't see both sides of a new word back to back.
REVERSE_DELAY = timedelta(days=1)
# Like Anki's "learn ahead": cards due within this window are shown when nothing else is due.
LEARN_AHEAD = timedelta(minutes=20)

DRAFT_FIELDS = ("lemma", "display", "reading", "pos", "translations", "example", "example_translation", "notes")


class Repo:
    def __init__(self, session: AsyncSession):
        self.s = session

    # --- users & decks ---

    async def ensure_user(
        self, tg_id: int, *, native_lang: str, timezone: str, target_lang: str
    ) -> tuple[User, Deck]:
        user = await self.s.get(User, tg_id)
        if user is None:
            # Several updates can arrive at once (e.g. after a restart): if another one created
            # the user first, the savepoint rolls back and we just load that row.
            await self._insert_ignoring_conflict(User(id=tg_id, native_lang=native_lang, timezone=timezone))
            user = await self.s.get(User, tg_id, populate_existing=True)
            assert user is not None
        deck = await self.s.get(Deck, user.active_deck_id) if user.active_deck_id else None
        if deck is None:
            deck = await self.switch_language(user, target_lang)
        return user, deck

    async def switch_language(self, user: User, lang: str) -> Deck:
        query = select(Deck).where(Deck.user_id == user.id, Deck.target_lang == lang)
        deck = await self.s.scalar(query)
        if deck is None:
            await self._insert_ignoring_conflict(Deck(user_id=user.id, target_lang=lang, name=get_lang(lang).name_ru))
            deck = await self.s.scalar(query)
            assert deck is not None
        user.active_deck_id = deck.id
        return deck

    # --- personas ---

    async def active_persona(self, user: User) -> Persona:
        """The persona the bot plays for this user; creates the default one (Roxy) on first use."""
        persona = await self.s.scalar(
            select(Persona).where(Persona.user_id == user.id, Persona.is_active.is_(True)).limit(1)
        )
        if persona is None:
            persona = await self.s.scalar(select(Persona).where(Persona.user_id == user.id).order_by(Persona.id).limit(1))
            if persona is None:
                persona = await self.add_persona(user, DEFAULT_CARD.model_dump(), activate=False)
            persona.is_active = True
            await self.s.flush()
        return persona

    async def add_persona(self, user: User, card: dict[str, Any], activate: bool = True) -> Persona:
        persona = Persona(user_id=user.id, name=card["name"][:100], source=(card.get("source") or "")[:200], card=card)
        self.s.add(persona)
        await self.s.flush()
        if activate:
            await self.activate_persona(user, persona.id)
        return persona

    async def list_personas(self, user: User) -> list[Persona]:
        return list(await self.s.scalars(select(Persona).where(Persona.user_id == user.id).order_by(Persona.id)))

    async def get_persona(self, user: User, persona_id: int) -> Persona | None:
        persona = await self.s.get(Persona, persona_id)
        return persona if persona is not None and persona.user_id == user.id else None

    async def activate_persona(self, user: User, persona_id: int) -> Persona | None:
        persona = await self.get_persona(user, persona_id)
        if persona is None:
            return None
        for other in await self.list_personas(user):
            other.is_active = other.id == persona_id
        await self.s.flush()
        return persona

    async def update_persona(self, persona: Persona, card: dict[str, Any]) -> None:
        persona.card = card
        persona.name = card["name"][:100]
        persona.source = (card.get("source") or "")[:200]
        await self.s.flush()

    async def delete_persona(self, user: User, persona_id: int) -> bool:
        """Delete a persona; the last one can't be deleted (the bot always plays someone)."""
        personas = await self.list_personas(user)
        target = next((p for p in personas if p.id == persona_id), None)
        if target is None or len(personas) == 1:
            return False
        was_active = target.is_active
        await self.s.execute(delete(PersonaArt).where(PersonaArt.persona_id == persona_id))
        await self.s.delete(target)
        await self.s.flush()
        if was_active:
            await self.active_persona(user)
        return True

    # --- persona arts ---

    async def set_avatar(self, persona: Persona, file_id: str | None, credit: str = "") -> None:
        persona.avatar_file_id = file_id
        persona.avatar_credit = credit
        await self.s.flush()

    async def cached_arts(self, persona_id: int, emotion: str) -> list[PersonaArt]:
        rows = await self.s.scalars(
            select(PersonaArt).where(PersonaArt.persona_id == persona_id, PersonaArt.emotion == emotion)
        )
        return list(rows)

    async def add_art(self, persona_id: int, emotion: str, post_id: str, file_id: str, credit: str) -> None:
        await self._insert_ignoring_conflict(
            PersonaArt(persona_id=persona_id, emotion=emotion, post_id=post_id, file_id=file_id, credit=credit)
        )

    async def _insert_ignoring_conflict(self, obj: object) -> None:
        try:
            async with self.s.begin_nested():
                self.s.add(obj)
        except IntegrityError:
            pass

    # --- words ---

    async def add_word(self, deck_id: int, draft: dict[str, Any], now: datetime) -> Word:
        word = Word(deck_id=deck_id, created_at=now, **{k: draft.get(k) or _empty(k) for k in DRAFT_FIELDS})
        self.s.add(word)
        await self.s.flush()
        for direction, due in (("fwd", now), ("rev", now + REVERSE_DELAY)):
            self.s.add(Card(word_id=word.id, direction=direction, due=due, fsrs=srs.new_card_state(now)))
        await self.s.flush()
        return word

    async def find_duplicates(self, deck_id: int, lemma: str) -> list[Word]:
        rows = await self.s.scalars(
            select(Word).where(Word.deck_id == deck_id, func.lower(Word.lemma) == lemma.strip().lower())
        )
        return list(rows)

    async def find_words(self, deck_id: int, query: str) -> list[Word]:
        q = query.strip().lower()
        rows = await self.s.scalars(
            select(Word)
            .where(Word.deck_id == deck_id, or_(func.lower(Word.lemma) == q, func.lower(Word.display) == q))
            .order_by(Word.created_at)
        )
        return list(rows)

    async def count_words_since(self, deck_id: int, since: datetime) -> int:
        stmt = select(func.count(Word.id)).where(Word.deck_id == deck_id, Word.created_at >= since)
        return await self.s.scalar(stmt) or 0

    async def previous_word_at(self, deck_id: int, word_id: int) -> datetime | None:
        """When the word added before this one was saved."""
        stmt = (
            select(Word.created_at)
            .where(Word.deck_id == deck_id, Word.id != word_id)
            .order_by(Word.created_at.desc())
            .limit(1)
        )
        return await self.s.scalar(stmt)

    async def get_word(self, word_id: int) -> Word | None:
        return await self.s.get(Word, word_id)

    async def list_words(self, deck_id: int, limit: int = 50) -> list[Word]:
        rows = await self.s.scalars(
            select(Word).where(Word.deck_id == deck_id).order_by(Word.created_at.desc(), Word.id.desc()).limit(limit)
        )
        return list(rows)

    async def count_words(self, deck_id: int) -> int:
        return await self.s.scalar(select(func.count(Word.id)).where(Word.deck_id == deck_id)) or 0

    async def delete_word(self, word_id: int) -> None:
        card_ids = select(Card.id).where(Card.word_id == word_id)
        await self.s.execute(delete(ReviewLog).where(ReviewLog.card_id.in_(card_ids)))
        await self.s.execute(delete(Card).where(Card.word_id == word_id))
        await self.s.execute(delete(Word).where(Word.id == word_id))

    # --- cards & reviews ---

    def _deck_cards(self, deck_id: int):
        return select(Card).join(Word, Card.word_id == Word.id).where(Word.deck_id == deck_id)

    async def next_due_card(self, deck_id: int, now: datetime, just_reviewed: int | None = None) -> Card | None:
        """Next card to show. The card that was just rated is not shown again ahead of time."""
        ahead = Card.due <= now + LEARN_AHEAD
        if just_reviewed is not None:
            ahead = ahead & ((Card.id != just_reviewed) | (Card.due <= now))
        stmt = self._deck_cards(deck_id).where(ahead).order_by(Card.due, Card.id).limit(1)
        return await self.s.scalar(stmt)

    async def count_due(self, deck_id: int, now: datetime) -> int:
        stmt = (
            select(func.count(Card.id))
            .join(Word, Card.word_id == Word.id)
            .where(Word.deck_id == deck_id, Card.due <= now)
        )
        return await self.s.scalar(stmt) or 0

    async def next_due_at(self, deck_id: int) -> datetime | None:
        stmt = (
            select(Card.due)
            .join(Word, Card.word_id == Word.id)
            .where(Word.deck_id == deck_id)
            .order_by(Card.due)
            .limit(1)
        )
        return await self.s.scalar(stmt)

    async def get_card(self, card_id: int) -> Card | None:
        return await self.s.get(Card, card_id)

    async def last_review_at(self, card_id: int) -> datetime | None:
        return await self.s.scalar(
            select(ReviewLog.reviewed_at)
            .where(ReviewLog.card_id == card_id)
            .order_by(ReviewLog.reviewed_at.desc())
            .limit(1)
        )

    async def record_review(
        self, card: Card, rating: int, new_state: dict[str, Any], new_due: datetime, now: datetime
    ) -> None:
        card.fsrs = new_state
        card.due = new_due
        self.s.add(ReviewLog(card_id=card.id, rating=rating, reviewed_at=now))
        await self.s.flush()

    async def review_times(self, deck_id: int, since: datetime) -> list[datetime]:
        stmt = (
            select(ReviewLog.reviewed_at)
            .join(Card, ReviewLog.card_id == Card.id)
            .join(Word, Card.word_id == Word.id)
            .where(Word.deck_id == deck_id, ReviewLog.reviewed_at >= since)
        )
        return list(await self.s.scalars(stmt))


def _empty(field: str) -> Any:
    return [] if field == "translations" else ""
