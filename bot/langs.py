from dataclasses import dataclass


@dataclass(frozen=True)
class Lang:
    code: str
    english: str  # for AI prompts
    name_ru: str  # «итальянский»
    adverb_ru: str  # «по-итальянски»
    flag: str


LANGS: dict[str, Lang] = {
    lang.code: lang
    for lang in [
        Lang("it", "Italian", "итальянский", "по-итальянски", "🇮🇹"),
        Lang("en", "English", "английский", "по-английски", "🇬🇧"),
        Lang("es", "Spanish", "испанский", "по-испански", "🇪🇸"),
        Lang("fr", "French", "французский", "по-французски", "🇫🇷"),
        Lang("de", "German", "немецкий", "по-немецки", "🇩🇪"),
        Lang("pt", "Portuguese", "португальский", "по-португальски", "🇵🇹"),
        Lang("ja", "Japanese", "японский", "по-японски", "🇯🇵"),
        Lang("ko", "Korean", "корейский", "по-корейски", "🇰🇷"),
        Lang("zh", "Chinese (Mandarin)", "китайский", "по-китайски", "🇨🇳"),
        Lang("tr", "Turkish", "турецкий", "по-турецки", "🇹🇷"),
        Lang("ru", "Russian", "русский", "по-русски", "🇷🇺"),
    ]
}


def get_lang(code: str) -> Lang:
    return LANGS.get(code) or Lang(code, code, code, f"на «{code}»", "🏳️")
