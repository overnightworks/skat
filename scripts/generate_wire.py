"""Write the browser's typed copy of the paths and answer tokens the Python app owns.

The Python constants own the paths and the enums own the tokens; this generator renders them as TypeScript constants.
`--check` writes nothing and fails when the committed file differs from the rendering or is
missing, so CI catches drift.
"""

import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

PRETTIER_WIDTH = 120  # the width prettier wraps the generated array at
REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "src"))

from skat.engine.bidding import VALID_BIDS  # noqa: E402
from skat.engine.tricks import ALL_POINTS  # noqa: E402
from skat.table.auction import AuctionAction  # noqa: E402
from skat.table.records import TABLE_ID_PATTERN  # noqa: E402
from skat.web.auction import (  # noqa: E402
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
)
from skat.web.constants import (  # noqa: E402
    ACCOUNT_CONSOLE_PATH,
    ACCOUNT_PATH,
    AUTH_START_PATH,
    CALL_MODE,
    LOGOUT_PATH,
    MODE_QUERY_NAME,
    NO_ACCESS_PATH,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
)
from skat.web.declaring import TABLE_DECLARATION_SUFFIX  # noqa: E402
from skat.web.playing import TABLE_CARD_SUFFIX  # noqa: E402
from skat.web.ready import TABLE_READY_SUFFIX  # noqa: E402
from skat.web.tables import (  # noqa: E402
    TABLE_EVENTS_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
    AwaitingToken,
    GameToken,
    PositionToken,
    RankToken,
    StageToken,
    SuitToken,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from enum import StrEnum

OUTPUT = Path("frontend/src/lib/wire.ts")
CHECK_FLAG = "--check"
HEADER = "// Generated from the Python path and token owners by scripts/generate_wire.py. Do not edit.\n"
TOKEN_TUPLES: dict[str, type[StrEnum]] = {
    "SUIT_TOKENS": SuitToken,
    "RANK_TOKENS": RankToken,
    "POSITION_TOKENS": PositionToken,
    "GAME_TOKENS": GameToken,
    "STAGE_TOKENS": StageToken,
    "AWAITING_TOKENS": AwaitingToken,
    "AUCTION_ACTION_TOKENS": AuctionAction,
}


def token_tuple(name: str, tokens: type[StrEnum]) -> str:
    listed = ", ".join(f'"{token.value}"' for token in tokens)
    return f"export const {name} = [{listed}] as const;\n"


def render() -> str:
    constants = {
        "AUTH_START_PATH": AUTH_START_PATH,
        "RETURN_PATH_QUERY_NAME": RETURN_PATH_QUERY_NAME,
        "SIGNED_IN_AGAIN_QUERY_NAME": SIGNED_IN_AGAIN_QUERY_NAME,
        "NO_ACCESS_PATH": NO_ACCESS_PATH,
        "MODE_QUERY_NAME": MODE_QUERY_NAME,
        "CALL_MODE": CALL_MODE,
        "LOGOUT_PATH": LOGOUT_PATH,
        "ACCOUNT_PATH": ACCOUNT_PATH,
        "ACCOUNT_CONSOLE_PATH": ACCOUNT_CONSOLE_PATH,
        "TABLES_PATH": TABLES_PATH,
        "TABLE_PAGE_PREFIX": TABLE_PAGE_PREFIX,
        "TABLE_ID_PATTERN": TABLE_ID_PATTERN,
        "TABLE_EVENTS_SUFFIX": TABLE_EVENTS_SUFFIX,
        "TABLE_SIT_SUFFIX": TABLE_SIT_SUFFIX,
        "TABLE_STAND_SUFFIX": TABLE_STAND_SUFFIX,
        "TABLE_DECLARATION_SUFFIX": TABLE_DECLARATION_SUFFIX,
        "TABLE_AUCTION_BID_SUFFIX": TABLE_AUCTION_BID_SUFFIX,
        "TABLE_AUCTION_HOLD_SUFFIX": TABLE_AUCTION_HOLD_SUFFIX,
        "TABLE_AUCTION_PASS_SUFFIX": TABLE_AUCTION_PASS_SUFFIX,
        "TABLE_AUCTION_PLAY_SUFFIX": TABLE_AUCTION_PLAY_SUFFIX,
        "TABLE_CARD_SUFFIX": TABLE_CARD_SUFFIX,
        "TABLE_READY_SUFFIX": TABLE_READY_SUFFIX,
    }
    paths = "".join(f'export const {name} = "{path}";\n' for name, path in constants.items())
    tuples = "".join(token_tuple(name, tokens) for name, tokens in TOKEN_TUPLES.items())
    wrapped_bids = textwrap.fill(
        ", ".join(map(str, VALID_BIDS)) + ",", width=PRETTIER_WIDTH, initial_indent="    ", subsequent_indent="    "
    )
    valid_bids = f"export const VALID_BIDS = [\n{wrapped_bids}\n] as const;\n"
    all_points = f"export const ALL_POINTS = {ALL_POINTS};\n"
    return HEADER + "\n" + paths + tuples + valid_bids + all_points


def main(arguments: Sequence[str], root: Path = REPOSITORY) -> int:
    target = root / OUTPUT
    rendered = render()
    if CHECK_FLAG in arguments:
        if not target.is_file() or target.read_text() != rendered:
            raise SystemExit(f"generate_wire: {target} out of date; run scripts/generate_wire.py without --check")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
