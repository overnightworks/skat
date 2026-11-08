"""Tests for the generator that writes the browser's typed texts from the German catalog."""

from typing import TYPE_CHECKING

import pytest

from scripts import generate_words

if TYPE_CHECKING:
    from pathlib import Path


def write_catalog(root: Path, entries: dict[str, str]) -> None:
    catalog = root / generate_words.CATALOG
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(
        'msgid ""\nmsgstr ""\n"Language: de\\n"\n\n'
        + "".join(f'msgid "{key}"\nmsgstr "{text}"\n\n' for key, text in entries.items())
    )


def test_main_check_committed_words_module_exits_clean() -> None:
    assert generate_words.main(["--check"]) == 0


def test_main_writes_every_catalog_text_under_its_key_and_a_following_check_passes(tmp_path: Path) -> None:
    write_catalog(tmp_path, {"newTable": "Neuer Tisch", "seatFree": "Frei"})

    assert generate_words.main([], root=tmp_path) == 0

    written = (tmp_path / generate_words.OUTPUT).read_text()
    assert 'newTable: "Neuer Tisch"' in written
    assert 'seatFree: "Frei"' in written
    assert generate_words.main(["--check"], root=tmp_path) == 0


def test_main_keeps_umlauts_readable(tmp_path: Path) -> None:
    write_catalog(tmp_path, {"loadFailed": "Der Tisch lässt sich nicht laden"})

    generate_words.main([], root=tmp_path)

    assert "lässt" in (tmp_path / generate_words.OUTPUT).read_text()


@pytest.mark.parametrize("translation", ["", "   "])
def test_main_fails_naming_the_key_whose_translation_is_empty(tmp_path: Path, translation: str) -> None:
    write_catalog(tmp_path, {"newTable": "Neuer Tisch", "seatFree": translation})

    with pytest.raises(SystemExit, match="seatFree"):
        generate_words.main([], root=tmp_path)

    assert not (tmp_path / generate_words.OUTPUT).exists()


def test_main_fails_naming_the_key_whose_translation_is_fuzzy(tmp_path: Path) -> None:
    write_catalog(tmp_path, {"newTable": "Neuer Tisch"})
    catalog = tmp_path / generate_words.CATALOG
    catalog.write_text(catalog.read_text() + '#, fuzzy\nmsgid "seatFree"\nmsgstr "Frei"\n')

    with pytest.raises(SystemExit, match="seatFree"):
        generate_words.main([], root=tmp_path)

    assert not (tmp_path / generate_words.OUTPUT).exists()


@pytest.mark.parametrize("stale_content", [None, "// edited by hand\n"])
def test_main_check_fails_for_a_missing_or_edited_module(tmp_path: Path, stale_content: str | None) -> None:
    write_catalog(tmp_path, {"newTable": "Neuer Tisch"})
    if stale_content is not None:
        (tmp_path / generate_words.OUTPUT).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / generate_words.OUTPUT).write_text(stale_content)

    with pytest.raises(SystemExit, match="out of date"):
        generate_words.main(["--check"], root=tmp_path)
