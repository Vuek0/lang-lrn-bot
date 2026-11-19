from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    owner_id: int
    # AI providers: any subset works; the chain is Groq → OpenAI → Gemini (see bot/ai/service.py).
    # Model lists are comma-separated: the first model is tried first, the next ones if it fails.
    groq_api_key: str = ""
    groq_models: str = "openai/gpt-oss-120b,qwen/qwen3.8-27b"
    groq_reasoning_effort: str = "medium"
    groq_transcribe_model: str = "whisper-large-v3-turbo"

    openai_api_key: str = ""
    openai_model: str = "gpt-6-luna"
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"

    gemini_api_key: str = ""
    gemini_models: str = "gemini-3.8-flash,gemini-3.5-flash-lite,gemini-3.5-flash"
    gemini_thinking_level: str = "low"

    database_url: str = "sqlite+aiosqlite:///data/bot.db"
    timezone: str = "Asia/Tashkent"
    native_lang: str = "ru"
    default_target_lang: str = "it"

    # Optional Danbooru account for character art (danbooru.donmai.us → My Account → API Key)
    danbooru_login: str = ""
    danbooru_api_key: str = ""

    # How the persona's reaction pictures look: "sticker" (small, 512px) or "photo" (full picture)
    reaction_style: Literal["sticker", "photo"] = "sticker"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
