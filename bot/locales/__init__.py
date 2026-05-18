from bot.locales.ru import STRINGS

DEFAULT_LOCALE = "ru"

_TABLES: dict[str, dict[str, str]] = {"ru": STRINGS}


def translate(key: str, locale: str = DEFAULT_LOCALE, **kwargs: object) -> str:
    table = _TABLES.get(locale) or _TABLES[DEFAULT_LOCALE]
    template = table.get(key, key)
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template
