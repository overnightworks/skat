import base64
import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from skat.web.secret_files import StartRefusedError

BUILD_DIRECTORY = Path(__file__).parent / "build"
SHELL_FILE = "index.html"
SIGNED_OUT_FILE = "login.html"
CALL_SIGN_IN_FILE = "login/call.html"
LOGIN_FAILED_FILE = "login-failed.html"
NO_ACCESS_FILE = "no-access.html"
APP_DIRECTORY = "_app"


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


def _scripts_of(page: bytes) -> _Scripts:
    scripts = _Scripts()
    scripts.feed(page.decode("utf-8"))
    scripts.close()
    return scripts


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


@dataclass(frozen=True)
class PageBuild:
    """What `make frontend` wrote: the pages the server answers with, and the script hashes their policy admits.

    The pages are held as read, so the served shell is the hashed shell even when a build rewrites the file
    while the server runs.
    """

    directory: Path
    shell: BuiltPage
    signed_out: BuiltPage
    login_failed: BuiltPage
    no_access: BuiltPage
    call_sign_in: BuiltPage
    script_hashes: tuple[str, ...]

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
        return cls(
            directory=directory,
            shell=BuiltPage.of(shell_bytes),
            signed_out=BuiltPage.of(signed_out_bytes),
            login_failed=BuiltPage.of(login_failed_bytes),
            no_access=BuiltPage.of(no_access_bytes),
            call_sign_in=BuiltPage.of(call_bytes),
            script_hashes=tuple(_script_hash(text) for text in (*shell_scripts.texts, *call_scripts.texts)),
        )
