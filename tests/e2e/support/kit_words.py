from design.words import text

from skat.web.words import SOURCE_LANGUAGE


def kit_text(key: str, **gaps: str) -> str:
    """The kit's text for `key` in the language Skat's pages are served in."""
    return text(SOURCE_LANGUAGE, key, **gaps)
