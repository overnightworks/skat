import base64
import hashlib
import posixpath
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

from skat.web.secret_files import StartRefusedError

if TYPE_CHECKING:
    from collections.abc import Iterable

BUILD_DIRECTORY = Path(__file__).parent / "build"
SHELL_FILE = "index.html"
SIGNED_OUT_FILE = "login.html"
CALL_SIGN_IN_FILE = "login/call.html"
LOGIN_FAILED_FILE = "login-failed.html"
NO_ACCESS_FILE = "no-access.html"
APP_PATH_PREFIX = "/_app/"
APP_DIRECTORY = "_app"
_CSS_URL = re.compile(r"""url\(\s*['"]?(/_app/[^'")\s]+)""")
_APP_PATH_IN_SCRIPT = re.compile(r"""["'](/_app/[^"'\s]+)["']""")
# A static import or re-export names its file after `from`, or right after a bare `import`; `import(` is dynamic.
_STATIC_IMPORT = re.compile(
    r"""\b(?:import|export)\b[^;"'`()]*?\bfrom\s*["']([^"']+)["']|\bimport\s*["']([^"']+)["']"""
)


class PageBuildMissingError(StartRefusedError):
    """The page build is not where the server expects it."""


class SignInPageScriptError(StartRefusedError):
    """A plain sign-in page carries a script, which only the call sign-in page may."""


class _Scripts(HTMLParser):
    """The number of `<script>` elements, and the text of every one without `src`, each joined from the chunks."""

    def __init__(self) -> None:
        super().__init__()
        self.element_count = 0
        self.texts: list[str] = []
        self._chunks: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.element_count += 1
        if tag == "script" and all(name != "src" for name, _ in attrs):
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._chunks is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._chunks is not None:
            self.texts.append("".join(self._chunks))
            self._chunks = None


class _Links(HTMLParser):
    """The `href` of every `<link>` with the given `rel`."""

    def __init__(self, rel: str) -> None:
        super().__init__()
        self._rel = rel
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "link" and values.get("rel") == self._rel and values.get("href"):
            self.hrefs.append(str(values["href"]))


def _scripts_of(page: bytes) -> _Scripts:
    scripts = _Scripts()
    scripts.feed(page.decode("utf-8"))
    scripts.close()
    return scripts


def _app_links(page: bytes, rel: str) -> frozenset[str]:
    links = _Links(rel)
    links.feed(page.decode("utf-8"))
    links.close()
    return _within_app(links.hrefs)


def _within_app(paths: Iterable[str]) -> frozenset[str]:
    normalized = (posixpath.normpath(path) for path in paths)
    return frozenset(path for path in normalized if path.startswith(APP_PATH_PREFIX))


def _static_imports(module: bytes, module_path: str) -> frozenset[str]:
    """The `/_app/` files that a module's static import and re-export declarations name."""
    return _within_app(
        posixpath.join(posixpath.dirname(module_path), first or second)
        for first, second in _STATIC_IMPORT.findall(module.decode("utf-8"))
    )


def _css_asset_urls(css: bytes) -> frozenset[str]:
    return frozenset(_CSS_URL.findall(css.decode("utf-8")))


def _script_hash(text: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


@dataclass(frozen=True)
class BuiltPage:
    """One page as `make frontend` wrote it, with the strong ETag of those bytes."""

    content: bytes
    etag: str

    @classmethod
    def of(cls, content: bytes) -> BuiltPage:
        return cls(content=content, etag=f'"{hashlib.sha256(content).hexdigest()}"')


def _read_app_file(directory: Path, path: str) -> bytes:
    file = directory / path.removeprefix("/")
    if not file.is_file():
        raise PageBuildMissingError(f"The page build at {directory} lacks {path}; run make frontend")
    return file.read_bytes()


def _module_closure(directory: Path, call_page: bytes, bootstrap_texts: Iterable[str]) -> frozenset[str]:
    """The modules that the call page's bootstrap and `modulepreload` links name, with their static imports."""
    pending = set(_app_links(call_page, "modulepreload")).union(
        _within_app(path for text in bootstrap_texts for path in _APP_PATH_IN_SCRIPT.findall(text))
    )
    closure: set[str] = set()
    while pending:
        module = pending.pop()
        closure.add(module)
        pending |= _static_imports(_read_app_file(directory, module), module) - closure
    return frozenset(closure)


@dataclass(frozen=True)
class PageBuild:
    """What `make frontend` wrote: the pages the server answers with, and what their policy and gate admit.

    The pages are held as read, so the served shell is the hashed shell even when a build rewrites the file
    while the server runs. `sign_in_assets` are the `/_app/` files a signed-out visitor may fetch: the stylesheets the
    four sign-in pages link, the `/_app/` files those stylesheets reference (the fonts), and the module files of the
    call sign-in page, the only one that runs a script (static imports only; a dynamic import target stays behind
    the sign-in).
    """

    directory: Path
    shell: BuiltPage
    signed_out: BuiltPage
    login_failed: BuiltPage
    no_access: BuiltPage
    call_sign_in: BuiltPage
    script_hashes: tuple[str, ...]
    sign_in_assets: frozenset[str]

    @property
    def app_directory(self) -> Path:
        return self.directory / APP_DIRECTORY

    @classmethod
    def load(cls, directory: Path) -> PageBuild:
        plain_files = (SIGNED_OUT_FILE, LOGIN_FAILED_FILE, NO_ACCESS_FILE)
        page_paths = [directory / name for name in (SHELL_FILE, *plain_files, CALL_SIGN_IN_FILE)]
        if not all(path.is_file() for path in page_paths) or not (directory / APP_DIRECTORY).is_dir():
            raise PageBuildMissingError(f"The page build is missing at {directory}; run make frontend")
        shell_bytes, signed_out_bytes, login_failed_bytes, no_access_bytes, call_bytes = (
            path.read_bytes() for path in page_paths
        )
        plain_pages = (signed_out_bytes, login_failed_bytes, no_access_bytes)
        for name, page in zip(plain_files, plain_pages, strict=True):
            if _scripts_of(page).element_count:
                raise SignInPageScriptError(f"The sign-in page {name} carries a script; only {CALL_SIGN_IN_FILE} may")
        shell_scripts = _scripts_of(shell_bytes)
        call_scripts = _scripts_of(call_bytes)
        stylesheets = frozenset[str]().union(*(_app_links(page, "stylesheet") for page in (*plain_pages, call_bytes)))
        fonts = frozenset[str]().union(
            *(_css_asset_urls(_read_app_file(directory, stylesheet)) for stylesheet in stylesheets)
        )
        return cls(
            directory=directory,
            shell=BuiltPage.of(shell_bytes),
            signed_out=BuiltPage.of(signed_out_bytes),
            login_failed=BuiltPage.of(login_failed_bytes),
            no_access=BuiltPage.of(no_access_bytes),
            call_sign_in=BuiltPage.of(call_bytes),
            script_hashes=tuple(_script_hash(text) for text in (*shell_scripts.texts, *call_scripts.texts)),
            sign_in_assets=stylesheets | fonts | _module_closure(directory, call_bytes, call_scripts.texts),
        )
