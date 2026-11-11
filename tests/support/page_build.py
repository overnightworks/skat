"""The committed page build the tests serve.

It holds a shell with one inline script, the three plain sign-in pages with their stylesheet, the font it
references, the call sign-in page with a bootstrap script and a module file it links, one immutable file, the
chunk carrying the route announcer markup and the version file.
"""

from pathlib import Path

from skat.web.page_build import PageBuild

FIXTURE_DIRECTORY = Path(__file__).parent / "page_build_fixture"
# The SHA-256 of the fixture shell's one inline script, written out so no test derives it through production code.
FIXTURE_SCRIPT_HASH = "sha256-4LKaLFjkbG7q9xKX2UaD3tcSyvjsmzchYiSkLO5EkO8="
# The SHA-256 of the style text of the fixture chunk's route announcer, written out for the same reason.
ANNOUNCER_STYLE_HASH = "sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo="
SIGN_IN_STYLESHEET = "/_app/immutable/assets/sign-in.css"
SIGN_IN_FONT = "/_app/immutable/assets/fixture-font.woff2"
# The SHA-256 of the fixture call page's one inline script.
CALL_PAGE_SCRIPT_HASH = "sha256-dml1HkUAI45VcVj2XqygWD0+6NIfezilpWE6AHzQkdE="
CALL_PAGE_MODULE = "/_app/immutable/entry/call.js"
IMMUTABLE_FILE = "/_app/immutable/x.js"
VERSION_FILE = "/_app/version.json"


def fixture_page_build() -> PageBuild:
    return PageBuild.load(FIXTURE_DIRECTORY)
