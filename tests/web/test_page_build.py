from typing import TYPE_CHECKING

import pytest

from skat.web.page_build import PageBuild, PageBuildMissingError
from skat.web.secret_files import StartRefusedError
from tests.support.page_build import (
    ANNOUNCER_STYLE_HASH,
    CALL_PAGE_SCRIPT_HASH,
    FIXTURE_DIRECTORY,
    FIXTURE_SCRIPT_HASH,
)

if TYPE_CHECKING:
    from pathlib import Path


SIGN_IN_PAGES = ("login.html", "login-failed.html", "no-access.html")
CALL_PAGE = "login/call.html"
EMPTY_PAGE = "<html></html>"
ANNOUNCER_STYLE = "position: absolute; width: 1px"
CHUNKS = "_app/immutable/chunks"


def announcer_chunk(style: str = ANNOUNCER_STYLE, attributes: str = 'aria-live="assertive"') -> str:
    return f'var a=template(`<div id="svelte-announcer" {attributes} style="{style}"><!></div>`);'


def write_chunk(root: Path, name: str, text: str) -> None:
    (root / CHUNKS).mkdir(parents=True, exist_ok=True)
    (root / CHUNKS / name).write_text(text, encoding="utf-8")


def build_with_shell(root: Path, shell: str, sign_in_page: str = EMPTY_PAGE, call_page: str = EMPTY_PAGE) -> Path:
    (root / "_app").mkdir(parents=True)
    (root / "login").mkdir()
    (root / "index.html").write_text(shell, encoding="utf-8")
    for name in SIGN_IN_PAGES:
        (root / name).write_text(sign_in_page, encoding="utf-8")
    (root / CALL_PAGE).write_text(call_page, encoding="utf-8")
    write_chunk(root, "announcer.js", announcer_chunk())
    return root


class TestLoad:
    def test_the_committed_fixture_loads_with_the_known_hash_of_its_one_inline_script(self):
        page_build = PageBuild.load(FIXTURE_DIRECTORY)

        assert page_build.directory == FIXTURE_DIRECTORY
        assert page_build.script_hashes == (FIXTURE_SCRIPT_HASH, CALL_PAGE_SCRIPT_HASH)

    def test_the_announcer_style_hash_is_the_known_one_of_the_fixture_chunk(self):
        assert PageBuild.load(FIXTURE_DIRECTORY).announcer_style_hash == ANNOUNCER_STYLE_HASH

    def test_the_announcer_style_hash_is_that_of_the_style_text_the_browser_sets(self, tmp_path):
        root = build_with_shell(tmp_path, EMPTY_PAGE)
        write_chunk(root, "announcer.js", announcer_chunk(style="content: &quot;a&quot; &amp; b"))

        assert PageBuild.load(root).announcer_style_hash == "sha256-oAiM+JIjGn/N6JGc5nBesq1haQCNhQxjavjeTnBaAVw="

    def test_the_same_announcer_style_in_two_chunks_loads(self, tmp_path):
        root = build_with_shell(tmp_path, EMPTY_PAGE)
        write_chunk(root, "other.js", announcer_chunk(attributes='aria-atomic="true"'))

        assert PageBuild.load(root).announcer_style_hash == "sha256-xsTtEarutAcxswPJ7Dh39bdibYH5aZAiRSjgNKIUIyM="

    def test_a_build_without_the_announcer_style_refuses_the_start_naming_the_announcer(self, tmp_path):
        root = build_with_shell(tmp_path, EMPTY_PAGE)
        (root / CHUNKS / "announcer.js").unlink()

        with pytest.raises(PageBuildMissingError, match="announcer"):
            PageBuild.load(root)

    def test_an_announcer_whose_style_is_not_an_attribute_refuses_the_start(self, tmp_path):
        root = build_with_shell(tmp_path, EMPTY_PAGE)
        write_chunk(root, "announcer.js", 'var a=`<div id="svelte-announcer"></div>`;')

        with pytest.raises(PageBuildMissingError, match="announcer"):
            PageBuild.load(root)

    def test_two_different_announcer_styles_refuse_the_start_naming_the_announcer(self, tmp_path):
        root = build_with_shell(tmp_path, EMPTY_PAGE)
        write_chunk(root, "other.js", announcer_chunk(style="width: 2px"))

        with pytest.raises(PageBuildMissingError, match="announcer"):
            PageBuild.load(root)

    @pytest.mark.parametrize(
        ("shell", "hashes"),
        [
            ("<html><body>no script</body></html>", ()),
            ('<script src="/a.js"></script>', ()),
            ("<script>first();</script>", ("sha256-zLkkCRwXnY9Po9RpPpnc0FGgkj110bMQ+s91j2btock=",)),
            (
                '<script>first();</script><script src="/a.js"></script><script>second();</script>',
                (
                    "sha256-zLkkCRwXnY9Po9RpPpnc0FGgkj110bMQ+s91j2btock=",
                    "sha256-dGCVYAQKA3St4oajZNnYqanOSQTbzydEw1qtGC2p8B4=",
                ),
            ),
            (
                "<script>if (a < b && c) { go(); }</script>",
                ("sha256-AN1wiKAb/Pu7jSZZAf3Ia9nFQlkK5Nhh7LQo7YqHHIY=",),
            ),
        ],
        ids=["none", "src-only", "one", "several", "text-the-parser-hands-over-in-chunks"],
    )
    def test_the_hashes_are_those_of_every_inline_script_in_order(self, tmp_path, shell, hashes):
        assert PageBuild.load(build_with_shell(tmp_path, shell)).script_hashes == hashes

    @pytest.mark.parametrize("shell", ["<html></html>", "<html>other</html>"])
    def test_the_shell_is_the_bytes_read_and_its_strong_etag_follows_them(self, tmp_path, shell):
        page_build = PageBuild.load(build_with_shell(tmp_path, shell))

        assert page_build.shell.content == shell.encode()
        assert page_build.shell.etag.startswith('"')
        assert page_build.shell.etag.endswith('"')

    def test_the_etag_of_known_bytes_is_the_quoted_sha256_of_them(self, tmp_path):
        page_build = PageBuild.load(build_with_shell(tmp_path, "<html></html>"))

        assert page_build.shell.etag == '"b633a587c652d02386c4f16f8c6f6aab7352d97f16367c3c40576214372dd628"'

    def test_a_shell_written_after_the_load_changes_neither_the_bytes_nor_the_hashes(self, tmp_path):
        root = build_with_shell(tmp_path, "<script>first();</script>")
        page_build = PageBuild.load(root)

        (root / "index.html").write_text("<script>second();</script>", encoding="utf-8")

        assert page_build.shell.content == b"<script>first();</script>"
        assert page_build.script_hashes == ("sha256-zLkkCRwXnY9Po9RpPpnc0FGgkj110bMQ+s91j2btock=",)

    def test_a_missing_directory_refuses_the_start_and_names_the_build_command(self, tmp_path):
        with pytest.raises(StartRefusedError, match="make frontend"):
            PageBuild.load(tmp_path / "absent")

    def test_a_directory_without_the_shell_refuses_the_start_and_names_the_build_command(self, tmp_path):
        (tmp_path / "_app").mkdir()

        with pytest.raises(StartRefusedError, match="make frontend"):
            PageBuild.load(tmp_path)

    def test_a_directory_without_the_app_files_refuses_the_start_and_names_the_build_command(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

        with pytest.raises(StartRefusedError, match="make frontend"):
            PageBuild.load(tmp_path)

    def test_the_sign_in_pages_are_the_bytes_read_with_strong_etags(self):
        page_build = PageBuild.load(FIXTURE_DIRECTORY)

        for page, name in (
            (page_build.signed_out, "login.html"),
            (page_build.login_failed, "login-failed.html"),
            (page_build.no_access, "no-access.html"),
        ):
            assert page.content == (FIXTURE_DIRECTORY / name).read_bytes()
            assert page.etag.startswith('"')
            assert page.etag.endswith('"')

    def test_the_call_sign_in_page_is_the_bytes_read_with_a_strong_etag(self):
        page = PageBuild.load(FIXTURE_DIRECTORY).call_sign_in

        assert page.content == (FIXTURE_DIRECTORY / CALL_PAGE).read_bytes()
        assert page.etag.startswith('"')
        assert page.etag.endswith('"')

    @pytest.mark.parametrize("page", SIGN_IN_PAGES)
    @pytest.mark.parametrize("script", ["<script>go();</script>", '<script src="/_app/a.js"></script>'])
    def test_a_plain_sign_in_page_with_a_script_refuses_the_start(self, tmp_path, page, script):
        root = build_with_shell(tmp_path, EMPTY_PAGE)
        (root / page).write_text(script, encoding="utf-8")

        with pytest.raises(StartRefusedError, match=page):
            PageBuild.load(root)

    @pytest.mark.parametrize("missing", [*SIGN_IN_PAGES, CALL_PAGE])
    def test_a_directory_without_a_sign_in_page_refuses_the_start_and_names_the_build_command(self, tmp_path, missing):
        root = build_with_shell(tmp_path, "<html></html>")
        (root / missing).unlink()

        with pytest.raises(StartRefusedError, match="make frontend"):
            PageBuild.load(root)
