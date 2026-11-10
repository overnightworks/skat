"""Tests for the generator that writes the browser's typed copy of the Python paths."""

from typing import TYPE_CHECKING

import pytest

from scripts import generate_wire
from skat.engine.bidding import VALID_BIDS
from skat.engine.tricks import ALL_POINTS
from skat.engine.value import Level
from skat.table.auction import AuctionAction
from skat.table.records import (
    SERIES_LENGTH_DEFAULT,
    SERIES_LENGTH_MAX,
    SERIES_LENGTH_MIN,
    SERIES_LENGTH_STEP,
    TABLE_ID_PATTERN,
    EndReason,
)
from skat.table.rules import CHAIRS_PER_TABLE
from skat.web.auction import (
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
)
from skat.web.call import CALL_ORIGIN_PATH
from skat.web.constants import (
    ACCOUNT_CONSOLE_PATH,
    ACCOUNT_PATH,
    AUTH_START_PATH,
    CALL_MODE,
    LOGOUT_PATH,
    MODE_QUERY_NAME,
    NO_ACCESS_PATH,
)
from skat.web.declaring import (
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
)
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.playing import TABLE_CARD_SUFFIX
from skat.web.ready import TABLE_READY_SUFFIX
from skat.web.tables import (
    TABLE_PAGE_PREFIX,
    TABLES_PATH,
    AnnouncementToken,
    AwaitingToken,
    GameToken,
    PositionToken,
    RankToken,
    StageToken,
    SuitToken,
)

if TYPE_CHECKING:
    from enum import StrEnum
    from pathlib import Path


def test_main_check_committed_wire_module_exits_clean() -> None:
    assert generate_wire.main(["--check"]) == 0


def test_render_names_every_path_the_page_uses() -> None:
    rendered = generate_wire.render()

    for name, path in [
        ("AUTH_START_PATH", AUTH_START_PATH),
        ("LOGOUT_PATH", LOGOUT_PATH),
        ("ACCOUNT_PATH", ACCOUNT_PATH),
        ("CALL_ORIGIN_PATH", CALL_ORIGIN_PATH),
        ("ACCOUNT_CONSOLE_PATH", ACCOUNT_CONSOLE_PATH),
        ("TABLES_PATH", TABLES_PATH),
        ("TABLE_PAGE_PREFIX", TABLE_PAGE_PREFIX),
        ("TABLE_DECLARING_TAKE_SUFFIX", TABLE_DECLARING_TAKE_SUFFIX),
        ("TABLE_DECLARING_PUT_BACK_SUFFIX", TABLE_DECLARING_PUT_BACK_SUFFIX),
        ("TABLE_DECLARING_DECLARE_SUFFIX", TABLE_DECLARING_DECLARE_SUFFIX),
        ("TABLE_AUCTION_BID_SUFFIX", TABLE_AUCTION_BID_SUFFIX),
        ("TABLE_AUCTION_HOLD_SUFFIX", TABLE_AUCTION_HOLD_SUFFIX),
        ("TABLE_AUCTION_PASS_SUFFIX", TABLE_AUCTION_PASS_SUFFIX),
        ("TABLE_AUCTION_PLAY_SUFFIX", TABLE_AUCTION_PLAY_SUFFIX),
        ("TABLE_CARD_SUFFIX", TABLE_CARD_SUFFIX),
        ("TABLE_LIST_SUFFIX", TABLE_LIST_SUFFIX),
        ("TABLE_READY_SUFFIX", TABLE_READY_SUFFIX),
        ("NO_ACCESS_PATH", NO_ACCESS_PATH),
        ("MODE_QUERY_NAME", MODE_QUERY_NAME),
        ("CALL_MODE", CALL_MODE),
        ("TABLE_ID_PATTERN", TABLE_ID_PATTERN),
    ]:
        assert any(name in line and f'"{path}"' in line for line in rendered.splitlines())


@pytest.mark.parametrize(
    ("name", "tokens"),
    [
        ("SUIT_TOKENS", SuitToken),
        ("RANK_TOKENS", RankToken),
        ("POSITION_TOKENS", PositionToken),
        ("GAME_TOKENS", GameToken),
        ("ANNOUNCEMENT_TOKENS", AnnouncementToken),
        ("STAGE_TOKENS", StageToken),
        ("AWAITING_TOKENS", AwaitingToken),
        ("AUCTION_ACTION_TOKENS", AuctionAction),
        ("LEVEL_TOKENS", Level),
        ("END_REASON_TOKENS", EndReason),
    ],
)
def test_render_lists_every_token_of_the_answer_as_a_const_tuple(name: str, tokens: type[StrEnum]) -> None:
    declaration = generate_wire.render().partition(f"export const {name} = ")[2].partition("as const;")[0]

    assert all(f'"{token.value}"' in declaration for token in tokens)


def test_render_names_the_chairs_of_a_table() -> None:
    assert f"export const CHAIRS_PER_TABLE = {CHAIRS_PER_TABLE};" in generate_wire.render()


def test_render_lists_every_valid_bid_in_rising_order() -> None:
    declaration = generate_wire.render().partition("VALID_BIDS = [")[2].partition("]")[0]

    assert [int(number) for number in declaration.replace("\n", " ").replace(",", " ").split()] == list(VALID_BIDS)


def test_render_names_the_card_points_of_a_whole_deck() -> None:
    assert f"export const ALL_POINTS = {ALL_POINTS};" in generate_wire.render().splitlines()


def test_render_names_the_bounds_step_and_default_of_a_series_length() -> None:
    lines = generate_wire.render().splitlines()

    assert f"export const SERIES_LENGTH_MIN = {SERIES_LENGTH_MIN};" in lines
    assert f"export const SERIES_LENGTH_MAX = {SERIES_LENGTH_MAX};" in lines
    assert f"export const SERIES_LENGTH_STEP = {SERIES_LENGTH_STEP};" in lines
    assert f"export const SERIES_LENGTH_DEFAULT = {SERIES_LENGTH_DEFAULT};" in lines


def test_main_writes_the_module_and_a_following_check_passes(tmp_path: Path) -> None:
    assert generate_wire.main([], root=tmp_path) == 0
    assert (tmp_path / generate_wire.OUTPUT).read_text() == generate_wire.render()
    assert generate_wire.main(["--check"], root=tmp_path) == 0


@pytest.mark.parametrize("stale_content", [None, "// edited by hand\n"])
def test_main_check_fails_for_a_missing_or_edited_module(tmp_path: Path, stale_content: str | None) -> None:
    if stale_content is not None:
        (tmp_path / generate_wire.OUTPUT).parent.mkdir(parents=True)
        (tmp_path / generate_wire.OUTPUT).write_text(stale_content)

    with pytest.raises(SystemExit, match="out of date"):
        generate_wire.main(["--check"], root=tmp_path)
