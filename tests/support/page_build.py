"""The committed page build the tests serve.

It holds a shell with one inline script, the three plain sign-in pages of each language with their stylesheet,
the font it references, the call sign-in page of each language with a bootstrap script of its own and a module file
it links, one immutable file, the chunk carrying the route announcer markup and the version file.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from skat.web.page_build import BUILT_LANG, PageBuild

if TYPE_CHECKING:
    from skat.web.words import Language

FIXTURE_DIRECTORY = Path(__file__).parent / "page_build_fixture"
# The SHA-256 of the fixture shell's one inline script, written out so no test derives it through production code.
FIXTURE_SCRIPT_HASH = "sha256-4LKaLFjkbG7q9xKX2UaD3tcSyvjsmzchYiSkLO5EkO8="
# The SHA-256 of the style text of the fixture chunk's route announcer, written out for the same reason.
ANNOUNCER_STYLE_HASH = "sha256-4Ko/a2xSVovnK+NHZgXVLdadpUbilwcSOx7rWnrn36U="
SIGN_IN_STYLESHEET = "/_app/immutable/assets/sign-in.css"
SIGN_IN_FONT = "/_app/immutable/assets/fixture-font.woff2"
# The SHA-256 of the one inline script of the fixture call page of each language.
CALL_PAGE_SCRIPT_HASHES: dict[Language, str] = {
    "de": "sha256-zDIxSY8t1OZk7xIXl+LTbtu+BlvisNbSIJcVZ+XQKvc=",
    "en": "sha256-1bK3WC9E32cp3YMD8pzAoRMJOoQqyDYwWzld82mgmOg=",
}
CALL_PAGE_MODULE = "/_app/immutable/entry/call.js"
IMMUTABLE_FILE = "/_app/immutable/x.js"
VERSION_FILE = "/_app/version.json"


def served_page(name: str, language: Language) -> bytes:
    """A fixture sign-in page as the server serves it in a language, its built `lang` replaced by that language."""
    path = FIXTURE_DIRECTORY / language / name
    return path.read_bytes().replace(BUILT_LANG, f'<html lang="{language}">'.encode())


def fixture_page_build() -> PageBuild:
    return PageBuild.load(FIXTURE_DIRECTORY)
