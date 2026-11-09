from typing import TYPE_CHECKING

import pytest

from skat.web.page_build import PageBuild, _css_asset_urls
from skat.web.secret_files import StartRefusedError
from tests.support.page_build import (
    CALL_PAGE_DYNAMIC_NODE,
    CALL_PAGE_IMPORTED_CHUNK,
    CALL_PAGE_MODULE,
    CALL_PAGE_SCRIPT_HASH,
    FIXTURE_DIRECTORY,
    FIXTURE_SCRIPT_HASH,
    IMMUTABLE_FILE,
    SIGN_IN_FONT,
    SIGN_IN_STYLESHEET,
)

if TYPE_CHECKING:
    from pathlib import Path


SIGN_IN_PAGES = ("login.html", "login-failed.html", "no-access.html")
CALL_PAGE = "login/call.html"
EMPTY_PAGE = "<html></html>"


def build_with_shell(root: Path, shell: str, sign_in_page: str = EMPTY_PAGE, call_page: str = EMPTY_PAGE) -> Path:
    (root / "_app").mkdir(parents=True)
    (root / "login").mkdir()
    (root / "index.html").write_text(shell, encoding="utf-8")
    for name in SIGN_IN_PAGES:
        (root / name).write_text(sign_in_page, encoding="utf-8")
    (root / CALL_PAGE).write_text(call_page, encoding="utf-8")
    return root


class TestLoad:
    def test_the_committed_fixture_loads_with_the_known_hash_of_its_one_inline_script(self):
        page_build = PageBuild.load(FIXTURE_DIRECTORY)

        assert page_build.directory == FIXTURE_DIRECTORY
        assert page_build.script_hashes == (FIXTURE_SCRIPT_HASH, CALL_PAGE_SCRIPT_HASH)

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

    @pytest.mark.parametrize(
        "call_page",
        [
            f'<script>go("{CALL_PAGE_MODULE}");</script>',
            f'<link rel="modulepreload" href="{CALL_PAGE_MODULE}">',
        ],
        ids=["bootstrap", "modulepreload"],
    )
    def test_the_call_page_hashes_its_bootstrap_and_admits_the_module_it_names(self, tmp_path, call_page):
        root = build_with_shell(tmp_path, EMPTY_PAGE, call_page=call_page)
        module = root / CALL_PAGE_MODULE.removeprefix("/")
        module.parent.mkdir(parents=True)
        module.write_text("", encoding="utf-8")

        assert PageBuild.load(root).sign_in_assets == {CALL_PAGE_MODULE}

    def test_the_sign_in_assets_hold_the_call_page_closure_of_static_imports_and_no_other_file(self):
        assets = PageBuild.load(FIXTURE_DIRECTORY).sign_in_assets

        assert {SIGN_IN_STYLESHEET, SIGN_IN_FONT, CALL_PAGE_MODULE, CALL_PAGE_IMPORTED_CHUNK} <= assets
        assert assets.isdisjoint({CALL_PAGE_DYNAMIC_NODE, IMMUTABLE_FILE})

    @pytest.mark.parametrize(
        "declaration",
        [
            'import{a as b}from"../chunks/c.js";',
            "import { a } from '../chunks/c.js';",
            'import"../chunks/c.js";',
            'export{a}from"../chunks/c.js";',
            'export*from"../chunks/c.js";',
            'import d,{a}from"../chunks/c.js";',
            'import*as ns from"../chunks/c.js";',
        ],
    )
    def test_every_form_of_static_import_names_a_module_of_the_closure(self, tmp_path, declaration):
        root = self.call_page_with_module(tmp_path, declaration)
        chunk = root / "_app/immutable/chunks/c.js"
        chunk.parent.mkdir()
        chunk.write_text("", encoding="utf-8")

        assert PageBuild.load(root).sign_in_assets == {CALL_PAGE_MODULE, "/_app/immutable/chunks/c.js"}

    @pytest.mark.parametrize(
        "text",
        ['import("../chunks/c.js");', "import(`../chunks/c.js`);", 'const c = "../chunks/c.js";', "import.meta.url;"],
    )
    def test_a_dynamic_import_or_a_plain_string_names_no_module_of_the_closure(self, tmp_path, text):
        root = self.call_page_with_module(tmp_path, text)

        assert PageBuild.load(root).sign_in_assets == {CALL_PAGE_MODULE}

    def test_a_module_named_outside_the_app_directory_is_no_module_of_the_closure(self, tmp_path):
        root = self.call_page_with_module(tmp_path, 'import"../../../outside.js";')

        assert PageBuild.load(root).sign_in_assets == {CALL_PAGE_MODULE}

    @pytest.mark.parametrize("named_by", ["the call page", "a module of the closure"])
    def test_a_module_named_but_missing_from_the_build_refuses_the_start_and_names_the_build_command(
        self, tmp_path, named_by
    ):
        if named_by == "the call page":
            root = build_with_shell(
                tmp_path, EMPTY_PAGE, call_page=f'<link rel="modulepreload" href="{CALL_PAGE_MODULE}">'
            )
        else:
            root = self.call_page_with_module(tmp_path, 'import"./gone.js";')

        with pytest.raises(StartRefusedError, match="make frontend"):
            PageBuild.load(root)

    @staticmethod
    def call_page_with_module(root: Path, module_text: str) -> Path:
        build_with_shell(root, EMPTY_PAGE, call_page=f'<link rel="modulepreload" href="{CALL_PAGE_MODULE}">')
        module = root / CALL_PAGE_MODULE.removeprefix("/")
        module.parent.mkdir(parents=True)
        module.write_text(module_text, encoding="utf-8")
        return root

    @pytest.mark.parametrize("page", SIGN_IN_PAGES)
    @pytest.mark.parametrize("script", ["<script>go();</script>", '<script src="/_app/a.js"></script>'])
    def test_a_plain_sign_in_page_with_a_script_refuses_the_start(self, tmp_path, page, script):
        root = build_with_shell(tmp_path, EMPTY_PAGE)
        (root / page).write_text(script, encoding="utf-8")

        with pytest.raises(StartRefusedError, match=page):
            PageBuild.load(root)

    def test_the_sign_in_assets_are_the_app_stylesheets_the_sign_in_pages_link_and_the_files_they_reference(
        self, tmp_path
    ):
        root = build_with_shell(tmp_path, "<html></html>")
        links = {
            "login.html": ("/_app/a.css", "/static/css/x.css"),
            "login-failed.html": ("/_app/a.css", "/_app/b.css"),
            "no-access.html": ("/_app/c.css",),
        }
        for name, hrefs in links.items():
            (root / name).write_text("".join(f'<link rel="stylesheet" href="{href}">' for href in hrefs))
        for stylesheet in ("a.css", "b.css", "c.css"):
            (root / "_app" / stylesheet).write_text("")
        (root / "_app" / "b.css").write_text("@font-face { src: url(/_app/f.woff2) }")

        assert PageBuild.load(root).sign_in_assets == {"/_app/a.css", "/_app/b.css", "/_app/c.css", "/_app/f.woff2"}

    @pytest.mark.parametrize("missing", [*SIGN_IN_PAGES, CALL_PAGE])
    def test_a_directory_without_a_sign_in_page_refuses_the_start_and_names_the_build_command(self, tmp_path, missing):
        root = build_with_shell(tmp_path, "<html></html>")
        (root / missing).unlink()

        with pytest.raises(StartRefusedError, match="make frontend"):
            PageBuild.load(root)

    def test_a_linked_app_stylesheet_missing_from_the_build_refuses_the_start_and_names_the_build_command(
        self, tmp_path
    ):
        root = build_with_shell(tmp_path, "<html></html>", '<link rel="stylesheet" href="/_app/gone.css">')

        with pytest.raises(StartRefusedError, match="make frontend"):
            PageBuild.load(root)


class TestCssAssetUrls:
    @pytest.mark.parametrize(
        "css",
        [
            b"a{src:url(/_app/f.woff2)}",
            b"a{src:url('/_app/f.woff2')}",
            b'a{src:url("/_app/f.woff2")}',
            b"a{src:url( /_app/f.woff2 )}",
        ],
    )
    def test_a_build_url_is_extracted_however_it_is_quoted(self, css):
        assert _css_asset_urls(css) == {"/_app/f.woff2"}

    @pytest.mark.parametrize(
        "other", [b"url(/static/f.woff2)", b"url(data:font/woff2;base64,AAAA)", b"url(fonts/f.woff2)", b"url(//_app/f)"]
    )
    def test_a_url_outside_the_build_is_not_extracted_beside_a_build_url(self, other):
        assert _css_asset_urls(b"a{src:url(/_app/f.woff2)}" + other) == {"/_app/f.woff2"}
