"""Character art from image boards: real artwork by real artists, never AI-generated.

- Danbooru (main): bans AI art by its rules; we also drop anything tagged as AI. Only rating:g (general).
  Anonymous search allows 2 tags, so extra filtering (AI tags, solo) happens on our side.
- Safebooru (fallback): an all-safe board.
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field

import aiohttp

log = logging.getLogger(__name__)

USER_AGENT = "lang-lrn-bot/0.1 (personal Telegram bot for language learning)"
TIMEOUT = aiohttp.ClientTimeout(total=20)
DANBOORU = "https://danbooru.donmai.us"
SAFEBOORU = "https://safebooru.org"
MAX_IMAGE_BYTES = 9_000_000  # Telegram photo upload limit is 10 MB
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}

AI_TAGS = {
    "ai-generated", "ai-assisted", "ai_generated", "ai_assisted", "ai-created",
    "stable_diffusion", "novelai", "midjourney", "nijijourney", "dall-e",
}
NOT_FOR_REACTIONS = {
    "comic", "2koma", "4koma", "manga", "speech_bubble", "multiple_views", "text_focus", "scenery", "chibi_inset",
}
# Persona emotion → image board tags, most fitting first; the next ones are tried when there are too few arts
EMOTIONS = {
    "happy": ["smile", "happy"],
    "excited": [":d", "excited", "smile"],
    "sad": ["sad", "tears", "frown", "pout"],
    "surprised": ["surprised", "wide-eyed", "open_mouth"],
    "proud": ["smug", "smile"],
}
ENOUGH_FOR_REACTIONS = 5


@dataclass
class Art:
    post_id: str  # "d123" (Danbooru) / "s456" (Safebooru)
    image_url: str
    page_url: str
    artist: str = ""
    source: str = ""
    tags: set[str] = field(default_factory=set)

    @property
    def is_ai(self) -> bool:
        return bool(self.tags & AI_TAGS)

    @property
    def credit(self) -> str:
        """HTML caption line crediting the artist."""
        from bot.utils import esc

        artist = esc(self.artist.replace("_", " ")) if self.artist else "неизвестный автор"
        link = self.source if self.source.startswith("http") else self.page_url
        return f'🎨 <a href="{esc(link)}">{artist}</a>'


def tag_candidates(name_en: str, guess: str = "") -> list[str]:
    """Possible Danbooru tags for a character: the AI's guess, 'first_last', 'last_first'."""
    out: list[str] = []
    for raw in [guess, name_en]:
        tag = re.sub(r"\s+", "_", raw.strip().lower())
        if tag and tag not in out:
            out.append(tag)
    parts = name_en.strip().lower().split()
    if len(parts) == 2:
        out.append(f"{parts[1]}_{parts[0]}")
    return out


def pick_tag(found: list[dict], name_en: str, source: str) -> str | None:
    """From Danbooru character tags, pick the best one for this name and series."""
    base = re.sub(r"\s+", "_", name_en.strip().lower())
    words = {w for w in re.split(r"[^a-z0-9]+", source.lower()) if len(w) > 2}
    best, best_score = None, -1.0
    for tag in found:
        name, count = tag.get("name", ""), tag.get("post_count", 0)
        if count <= 0:  # aliases and empty tags
            continue
        score = float(count)
        qualifier = re.search(r"_\((.+)\)$", name)
        if qualifier and words:
            if any(w in qualifier.group(1) for w in words):
                score *= 10  # rem_(re:zero) for "Re:Zero"
            else:
                continue  # satoru_gojo_(racehorse) is not from Jujutsu Kaisen
        if name == base or name.startswith(base + "_("):
            score *= 5
        if score > best_score:
            best, best_score = name, score
    return best


async def find_character_tag(name_en: str, source: str = "", guess: str = "") -> str | None:
    """Resolve a character name to a Danbooru character tag (category 4). None if not found."""
    try:
        async with _session() as http:
            for candidate in tag_candidates(name_en, guess):
                found = await _get_json(
                    http, f"{DANBOORU}/tags.json",
                    {"search[name_matches]": f"{candidate}*", "search[category]": "4",
                     "search[order]": "count", "limit": "10"},
                )
                if tag := pick_tag(found, name_en or guess, source):
                    return tag
            return None
    except Exception as exc:
        log.info("Danbooru tag lookup failed for %s: %r", name_en, exc)
        return None


def _danbooru_art(post: dict) -> Art | None:
    url = post.get("large_file_url") or post.get("file_url")
    if not url or post.get("file_ext") not in IMAGE_EXTS or post.get("is_banned") or post.get("rating") != "g":
        return None
    tags = set(post.get("tag_string", "").split())
    return Art(
        post_id=f"d{post['id']}",
        image_url=url,
        page_url=f"{DANBOORU}/posts/{post['id']}",
        artist=post.get("tag_string_artist", "").split(" ")[0],
        source=post.get("source", ""),
        tags=tags,
    )


def _safebooru_art(post: dict) -> Art | None:
    url = post.get("sample_url") or post.get("file_url")
    if not url or post.get("image", "").rsplit(".", 1)[-1].lower() not in IMAGE_EXTS:
        return None
    return Art(
        post_id=f"s{post['id']}",
        image_url=url,
        page_url=f"{SAFEBOORU}/index.php?page=post&s=view&id={post['id']}",
        source=post.get("source", ""),
        tags=set(post.get("tags", "").split()),
    )


def is_clean_solo(art: Art) -> bool:
    """One character, no comic panels or speech bubbles: works as a small reaction picture."""
    return "solo" in art.tags and not art.tags & NOT_FOR_REACTIONS


async def search_arts(tag: str, emotion: str | None = None, limit: int = 40, solo_only: bool = False) -> list[Art]:
    """Safe, non-AI arts of a character, solo ones first. Never raises.

    With an emotion, its tags are tried in order until enough arts are collected.
    """
    result: list[Art] = []
    seen: set[str] = set()
    for second in EMOTIONS.get(emotion or "", ["solo"]):
        for art in await _search(tag, second, limit):
            if art.post_id not in seen and (is_clean_solo(art) or not solo_only):
                seen.add(art.post_id)
                result.append(art)
        if len(result) >= ENOUGH_FOR_REACTIONS:
            break
    return result


async def _search(tag: str, second: str, limit: int) -> list[Art]:
    arts: list[Art] = []
    try:
        async with _session() as http:
            posts = await _get_json(
                http, f"{DANBOORU}/posts.json", {"tags": f"{tag} {second} rating:g", "limit": str(limit)}
            )
            arts = [a for a in map(_danbooru_art, posts) if a and not a.is_ai]
            if len(arts) < 3:
                posts = await _get_json(
                    http, f"{SAFEBOORU}/index.php",
                    {"page": "dapi", "s": "post", "q": "index", "json": "1", "limit": str(limit),
                     "tags": f"{tag} {second} -ai-generated -ai-assisted"},
                )
                arts += [a for a in map(_safebooru_art, posts or []) if a and not a.is_ai]
    except Exception as exc:
        log.info("art search failed for %s %s: %r", tag, second, exc)
    random.shuffle(arts)
    arts.sort(key=lambda a: "solo" not in a.tags)  # stable: solo first, random within groups
    return arts


async def download(art: Art) -> bytes | None:
    try:
        async with _session() as http, http.get(art.image_url) as response:
            response.raise_for_status()
            if not response.headers.get("content-type", "").startswith("image/"):
                return None
            data = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                data += chunk
                if len(data) > MAX_IMAGE_BYTES:
                    return None
            return bytes(data)
    except Exception as exc:
        log.info("image download failed %s: %r", art.image_url, exc)
        return None


async def download_many(arts: list[Art], count: int) -> list[tuple[Art, bytes]]:
    """Download until `count` images succeed (in parallel batches)."""
    result: list[tuple[Art, bytes]] = []
    queue = list(arts)
    while queue and len(result) < count:
        batch, queue = queue[: count - len(result)], queue[count - len(result):]
        for art, data in zip(batch, await asyncio.gather(*(download(a) for a in batch))):
            if data:
                result.append((art, data))
    return result


def _session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})


async def _get_json(http: aiohttp.ClientSession, url: str, params: dict) -> list:
    async with http.get(url, params=params) as response:
        response.raise_for_status()
        data = await response.json(content_type=None)
        return data if isinstance(data, list) else []
