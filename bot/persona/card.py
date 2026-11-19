"""Persona card: who the bot plays. Stored as JSON in the personas table."""

import random
import re

from pydantic import BaseModel, field_validator

from bot.utils import esc


def _clean_list(value: object) -> object:
    if isinstance(value, list):
        return [str(v).strip() for v in value if v and str(v).strip()]
    return value


class PersonaPhrases(BaseModel):
    """Short canned lines, generated once per persona, so buttons don't need an AI call."""

    greeting: list[str] = []
    thinking: list[str] = []
    saved: list[str] = []
    correct: list[str] = []
    wrong: list[str] = []
    review_done: list[str] = []

    @field_validator("*", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _clean_list(value)


class PersonaCard(BaseModel):
    name: str
    name_en: str = ""  # English/romaji name, for art search
    booru_tag: str = ""  # the AI's guess of the Danbooru tag
    source: str = ""  # "KonoSuba", or empty for an original character
    gender: str = ""  # female / male / other
    appearance: str = ""
    personality: str = ""
    speech_style: str = ""
    address_user: str = ""  # how they call the learner
    catchphrases: list[str] = []
    praise_style: str = ""
    support_style: str = ""
    never: str = ""  # what they would never say or do
    emoji: str = ""  # emojis they like to use
    phrases: PersonaPhrases = PersonaPhrases()

    @field_validator("catchphrases", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _clean_list(value)

    @field_validator(
        "name_en", "booru_tag", "source", "gender", "appearance", "personality", "speech_style", "address_user",
        "praise_style", "support_style", "never", "emoji", mode="before",
    )
    @classmethod
    def _none_to_empty(cls, value: object) -> object:
        return "" if value is None else value

    @property
    def title(self) -> str:
        return f"{self.name} ({self.source})" if self.source else self.name


DEFAULT_CARD = PersonaCard(
    name="Рокси",
    source="",
    gender="female",
    appearance="Девушка-аниме с короткими голубыми волосами, хитрым подмигиванием и итальянским шарфиком.",
    personality="Милая, весёлая и немного озорная. Искренне радуется каждому успеху ученика, никогда не ругает за ошибки, обожает Италию, пасту и красивые слова.",
    speech_style="Говорит живо и тепло, короткими фразами, часто вставляет итальянские словечки (Bravo!, Dai!, Mamma mia!). Любит эмодзи, но в меру.",
    address_user="«ты», иногда ласково «caro/cara» или «studente mio»",
    catchphrases=["Dai, ce la fai!", "Mamma mia, какое слово!", "Bravissimo!"],
    praise_style="Бурно радуется, хвалит по-итальянски, может подмигнуть 😉",
    support_style="Подбадривает: ошибки — это нормально, вместе разберёмся.",
    never="Никогда не грубит, не высмеивает ошибки и не говорит скучным канцелярским языком.",
    emoji="✨😉🍝🇮🇹💫",
    phrases=PersonaPhrases(
        greeting=["Ciao! 👋 Я Рокси, буду учить с тобой итальянский ✨", "Ciao ciao! Рокси на связи 😉"],
        thinking=["Секундочку, смотрю… 🔎", "Так-так, сейчас проверю 🤔", "Листаю словарик… 📖"],
        saved=["Сохранила! Bravo! 🎉", "Записала в колоду ✨", "Готово! Ещё одно слово наше 😉"],
        correct=["Bravissimo! ✨", "Perfetto! 💫", "Вот это да, молодец! 🎉"],
        wrong=["Ничего, в следующий раз точно! 💪", "Dai, ещё повторим 😉", "Ошибки — это нормально ✨"],
        review_done=["На сейчас всё! Ты супер 🎉", "Всё повторили, bravo! ✨"],
    ),
)


def phrase(card: PersonaCard, kind: str, fallback: list[str]) -> str:
    options: list[str] = getattr(card.phrases, kind, None) or fallback
    return random.choice(options)


def render_card(card: PersonaCard) -> str:
    rows = [f"🎭 <b>{esc(card.name)}</b>" + (f" — <i>{esc(card.source)}</i>" if card.source else " — <i>свой персонаж</i>")]
    fields = [
        ("👤 Внешность", card.appearance),
        ("💫 Характер", card.personality),
        ("🗣 Манера речи", card.speech_style),
        ("🫵 Обращается к тебе", card.address_user),
        ("📣 Коронные фразы", "; ".join(f"«{c}»" for c in card.catchphrases)),
        ("🫶 Хвалит", card.praise_style),
        ("🤝 Подбадривает", card.support_style),
        ("🚫 Никогда", card.never),
    ]
    rows += [f"\n<b>{title}:</b> {esc(value)}" for title, value in fields if value]
    if card.phrases.greeting:
        rows.append(f"\n💬 <i>{esc(card.phrases.greeting[0])}</i>")
    return "\n".join(rows)


_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])[*_](?!\s)(.+?)(?<!\s)[*_](?![\w*])")


def markdown_to_html(text: str) -> str:
    """Model replies use light markdown; Telegram wants HTML. Escape first, then convert."""
    html = esc(text.strip())
    html = _BOLD.sub(r"<b>\1</b>", html)
    html = _ITALIC.sub(r"<i>\1</i>", html)
    html = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", html, flags=re.MULTILINE)
    return html
