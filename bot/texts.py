"""All user-facing texts in one place, so a persona can restyle them later."""

import random

from bot.langs import Lang
from bot.utils import esc

STALE = "Эта кнопка уже неактуальна 🙂"
AI_ERROR = "Ой, у меня не получилось достучаться до AI 😿 Попробуй ещё раз чуть позже."
TOO_LONG = "Это длинновато 😅 Пришли одно слово или короткую фразу."

THINKING = ["Секундочку, смотрю… 🔎", "Так-так, сейчас проверю… 🤔", "Листаю словарик… 📖"]
SAVED = ["Сохранила! 🎉", "Готово, слово в колоде! ✨", "Записала! 📝"]


def pick(options: list[str]) -> str:
    return random.choice(options)


def help_text(lang: Lang, greeting: str) -> str:
    return (
        f"{esc(greeting)}\n\nСейчас учим: {lang.flag} <b>{lang.name_ru}</b>.\n\n"
        "📝 Пришли слово (текстом или голосом) — переведу, проверю и сохраню.\n"
        "💬 Спроси что угодно — «объясни congiuntivo», «как сказать „я опоздал“?» — отвечу.\n\n"
        "/review — повторить карточки\n"
        "/list — мои слова\n"
        "/stats — статистика\n"
        "/delete <i>слово</i> — удалить слово\n"
        "/lang — сменить язык\n"
        "/persona — выбрать или создать персонажа\n"
        "/practice — режим разговорной практики\n"
        "/stickers — какие стикеры присылает персонаж\n"
        "/remind — напоминания\n"
        "/memory — что персонаж помнит о тебе"
    )


def render_word(w: dict, *, show_notes: bool = True) -> str:
    """Card body. Accepts a draft dict or a Word converted with word_to_dict()."""
    lines = [f"<b>{esc(w['display'] or w['lemma'])}</b>" + (f"  <i>{esc(w['pos'])}</i>" if w.get("pos") else "")]
    if w.get("reading"):
        lines.append(f"🔤 {esc(w['reading'])}")
    if w.get("translations"):
        lines.append("➜ " + esc("; ".join(w["translations"])))
    if w.get("example"):
        lines.append(f"\n📝 <i>{esc(w['example'])}</i>")
        if w.get("example_translation"):
            lines.append(f"     {esc(w['example_translation'])}")
    if show_notes and w.get("notes"):
        lines.append(f"\n💡 {esc(w['notes'])}")
    return "\n".join(lines)


def word_to_dict(word) -> dict:
    return {
        "lemma": word.lemma,
        "display": word.display,
        "reading": word.reading,
        "pos": word.pos,
        "translations": list(word.translations or []),
        "example": word.example,
        "example_translation": word.example_translation,
        "notes": word.notes,
    }
