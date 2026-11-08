from pathlib import Path

from babel.messages.pofile import read_po

CATALOG = Path(__file__).resolve().parents[3] / "frontend/src/lib/catalogs/de.po"


def catalog_text(key: str) -> str:
    """The German catalog's text for `key`, as the page shows it."""
    with CATALOG.open("rb") as catalog:
        return str(read_po(catalog, locale="de")[key].string)
