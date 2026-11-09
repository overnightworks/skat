"""The committed page build the tests serve.

It holds a shell with one inline script, the three plain sign-in pages with their stylesheet, the font it
references, the call sign-in page with a bootstrap script and a module file it links, one immutable file and the
version file.
"""

from pathlib import Path

from skat.web.page_build import PageBuild

FIXTURE_DIRECTORY = Path(__file__).parent / "page_build_fixture"
# The SHA-256 of the fixture shell's one inline script, written out so no test derives it through production code.
FIXTURE_SCRIPT_HASH = "sha256-4LKaLFjkbG7q9xKX2UaD3tcSyvjsmzchYiSkLO5EkO8="
SIGN_IN_STYLESHEET = "/_app/immutable/assets/sign-in.css"
SIGN_IN_FONT = "/_app/immutable/assets/fixture-font.woff2"
# The SHA-256 of the fixture call page's one inline script.
CALL_PAGE_SCRIPT_HASH = "sha256-YIj8WEkmvGV4lNTGNi6YpvYk6Bdf9o1DTCLJYDodVq8="
CALL_PAGE_MODULE = "/_app/immutable/entry/call.js"
IMMUTABLE_FILE = "/_app/immutable/x.js"
VERSION_FILE = "/_app/version.json"


def fixture_page_build() -> PageBuild:
    return PageBuild.load(FIXTURE_DIRECTORY)
