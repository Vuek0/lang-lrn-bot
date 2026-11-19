"""Persona pictures in chat: avatar candidates and emotion reactions, cached by Telegram file_id."""

import hashlib
import logging
import random

from aiogram.types import BufferedInputFile, InputMediaPhoto, Message

from bot.db.models import Persona
from bot.db.repo import Repo
from bot.images import booru
from bot.images.sticker import to_sticker
from bot.persona.card import PersonaCard

log = logging.getLogger(__name__)

NO_TAG = "-"  # art_tag value meaning "searched, nothing found" — don't search again
REUSE_AFTER = 6  # with this many cached arts for an emotion, stop downloading new ones
AVATAR_CHOICES = 6

# "sticker": small 512px stickers (default) or "photo": full pictures. Set from REACTION_STYLE at startup.
STYLE = "sticker"

# How often a reaction picture accompanies an event (1.0 = always). Stickers are small, so they come more often.
# Words get a picture only on milestones (always), not on every save; questions never get one.
CHANCE = {"review_done": 1.0, "milestone": 1.0, "wrong": 0.25, "correct": 0.12, "chat": 0.35}
STICKER_CHANCE = {"review_done": 1.0, "milestone": 1.0, "wrong": 0.35, "correct": 0.25, "chat": 0.65}
EVENT_EMOTION = {"review_done": "happy", "milestone": "excited", "wrong": "sad", "correct": "happy", "chat": "happy"}

# Personas without arts (original characters) use their avatar as the one sticker — but not on every
# review card, where the same picture again and again would get boring.
AVATAR_EVENTS = {"chat", "milestone", "review_done"}
AVATAR_STICKER = "st:avatar"


def caption(text_html: str) -> str:
    """Just the persona's text, nothing under the picture. Telegram limits captions to 1024 chars."""
    return text_html if len(text_html) <= 1024 else text_html[:1023] + "…"


async def resolve_tag(persona: Persona, card: PersonaCard) -> str | None:
    """The character's art tag; looked up once and remembered on the persona row."""
    if persona.art_tag:
        return None if persona.art_tag == NO_TAG else persona.art_tag
    if not (card.name_en or card.booru_tag):  # original character: nothing to search for
        return None
    tag = await booru.find_character_tag(card.name_en or card.booru_tag, card.source, card.booru_tag)
    persona.art_tag = tag or NO_TAG
    return tag


async def send_avatar_candidates(
    message: Message, persona: Persona, card: PersonaCard, exclude: set[str] = frozenset()
) -> list[dict]:
    """Send an album of arts to choose from. Returns [{file_id, credit, post_id}], empty if none found."""
    tag = await resolve_tag(persona, card)
    if not tag:
        return []
    arts = [a for a in await booru.search_arts(tag) if a.post_id not in exclude]
    downloaded = await booru.download_many(arts, AVATAR_CHOICES)
    if not downloaded:
        return []
    media = [
        InputMediaPhoto(media=BufferedInputFile(data, filename=f"{art.post_id}.jpg"), caption=f"{i + 1}")
        for i, (art, data) in enumerate(downloaded)
    ]
    sent = await message.answer_media_group(media)
    return [
        {"file_id": msg.photo[-1].file_id, "credit": art.credit, "post_id": art.post_id}
        for msg, (art, _) in zip(sent, downloaded)
        if msg.photo
    ]


async def send_reaction(
    message: Message, repo: Repo, persona: Persona, card: PersonaCard, event: str, text_html: str = "",
    force: bool = False, emotion: str | None = None,
) -> bool:
    """Maybe send a picture of the persona for an event (and the text, if any).

    True if a picture was sent — then the text was sent too; False means the caller sends the text itself.
    Never raises.
    """
    stickers = STYLE == "sticker"
    chance = (STICKER_CHANCE if stickers else CHANCE).get(event, 0)
    if not force and random.random() > chance:
        return False
    try:
        tag = await resolve_tag(persona, card)
        if not tag:  # an original character without arts: the avatar can still be a sticker
            if event in AVATAR_EVENTS:
                return await _avatar_reaction(message, repo, persona, text_html, stickers)
            return False
        emotion = emotion or EVENT_EMOTION.get(event, "happy")
        cache_key = f"st:{emotion}" if stickers else emotion  # stickers and photos have separate file_ids
        cached = await repo.cached_arts(persona.id, cache_key)

        if cached and (len(cached) >= REUSE_AFTER or random.random() < 0.5):
            await _send(message, random.choice(cached).file_id, text_html, stickers)
            return True

        known = {a.post_id for a in cached}
        # Emotion searches can't also ask for "solo" (2-tag limit), so fetch more and filter on our side.
        found = await booru.search_arts(tag, emotion, limit=100, solo_only=True)
        fresh = [a for a in found if a.post_id not in known]
        for art, data in await booru.download_many(fresh[:6], 1):
            if stickers and (data := to_sticker(data)) is None:
                continue
            file_id = await _send(message, BufferedInputFile(data, filename=f"{art.post_id}.webp"), text_html, stickers)
            await repo.add_art(persona.id, cache_key, art.post_id, file_id, art.credit)
            return True

        if cached:  # nothing new found: reuse what we have
            await _send(message, random.choice(cached).file_id, text_html, stickers)
            return True
        return False
    except Exception:
        log.exception("reaction picture failed")
        return False


async def _avatar_reaction(message: Message, repo: Repo, persona: Persona, text_html: str, stickers: bool) -> bool:
    """The persona's avatar as a sticker (made once, then reused by file_id)."""
    if not persona.avatar_file_id:
        return False
    if not stickers:
        await message.answer_photo(persona.avatar_file_id, caption=caption(text_html))
        return True
    post_id = "av" + hashlib.md5(persona.avatar_file_id.encode()).hexdigest()[:24]  # changes with the avatar
    cached = [a for a in await repo.cached_arts(persona.id, AVATAR_STICKER) if a.post_id == post_id]
    if cached:
        await _send(message, cached[0].file_id, text_html, True)
        return True
    buffer = await message.bot.download(persona.avatar_file_id)
    data = to_sticker(buffer.read()) if buffer else None
    if data is None:
        return False
    file_id = await _send(message, BufferedInputFile(data, filename="avatar.webp"), text_html, True)
    await repo.add_art(persona.id, AVATAR_STICKER, post_id, file_id, "")
    return True


async def _send(message: Message, picture: str | BufferedInputFile, text_html: str, sticker: bool) -> str:
    """Send a reaction; returns the Telegram file_id of the picture for the cache."""
    if sticker:
        sent = await message.answer_sticker(picture)
        if text_html:  # stickers have no captions: the text goes right below
            await message.answer(text_html)
        return sent.sticker.file_id
    sent = await message.answer_photo(picture, caption=caption(text_html))
    return sent.photo[-1].file_id
