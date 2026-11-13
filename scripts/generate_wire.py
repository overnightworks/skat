"""Write the browser's typed copy of the paths and answer tokens the Python app owns.

The Python constants own the paths and the enums own the tokens; this generator renders them as TypeScript constants.
`--check` writes nothing and fails when the committed file differs from the rendering or is
missing, so CI catches drift.
"""

import json
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

PRETTIER_WIDTH = 120  # the width prettier wraps the generated array at
REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "src"))

from skat.engine.bidding import VALID_BIDS  # noqa: E402
from skat.engine.bock import BockOverlap, BockTrigger  # noqa: E402
from skat.engine.kontra import KontraDeadline, KontraReach, KontraSayer, Word  # noqa: E402
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschScoring  # noqa: E402
from skat.engine.schieberamsch import GrandHandRule, PushingRule  # noqa: E402
from skat.engine.tricks import ALL_POINTS  # noqa: E402
from skat.engine.value import Level  # noqa: E402
from skat.table.auction import AuctionAction  # noqa: E402
from skat.table.awaiting import WaitingCase  # noqa: E402
from skat.table.game_list import GameEnding  # noqa: E402
from skat.table.records import (  # noqa: E402
    SERIES_LENGTH_DEFAULT,
    SERIES_LENGTH_MAX,
    SERIES_LENGTH_MIN,
    SERIES_LENGTH_STEP,
    TABLE_ID_PATTERN,
    EndReason,
    RamschOccasion,
)
from skat.table.rule_sets import SWITCH_ON_OPTIONS  # noqa: E402
from skat.table.rules import CHAIRS_PER_TABLE  # noqa: E402
from skat.web.abort import TABLE_ABORT_AGREE_SUFFIX, TABLE_ABORT_REFUSE_SUFFIX  # noqa: E402
from skat.web.auction import (  # noqa: E402
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
)
from skat.web.call import CALL_ORIGIN_PATH  # noqa: E402
from skat.web.calling import TABLE_AGENT_CALL_SUFFIX, TABLE_AGENT_SEND_AWAY_SUFFIX, TABLE_AGENTS_SUFFIX  # noqa: E402
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
    VERSION_FILE_PATH,
)
from skat.web.declaring import (  # noqa: E402
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
)
from skat.web.game_list import TABLE_LIST_SUFFIX  # noqa: E402
from skat.web.kontra import TABLE_KONTRA_SUFFIX, TABLE_NO_WORD_SUFFIX  # noqa: E402
from skat.web.lobby import LOBBY_EVENTS_PATH  # noqa: E402
from skat.web.playing import (  # noqa: E402
    TABLE_CARD_SUFFIX,
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
)
from skat.web.pushing import (  # noqa: E402
    TABLE_PUSHING_GRAND_HAND_SUFFIX,
    TABLE_PUSHING_PUSH_SUFFIX,
    TABLE_PUSHING_PUT_BACK_SUFFIX,
    TABLE_PUSHING_TAKE_SUFFIX,
)
from skat.web.ready import TABLE_READY_SUFFIX  # noqa: E402
from skat.web.rule_sets import RULE_SETS_PATH  # noqa: E402
from skat.web.table_options import options_answer_of  # noqa: E402
from skat.web.tables import (  # noqa: E402
    TABLE_EVENTS_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
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
    from collections.abc import Sequence
    from enum import StrEnum

    from pydantic import JsonValue

OUTPUT = Path("frontend/src/lib/wire.ts")
CHECK_FLAG = "--check"
HEADER = "// Generated from the Python path and token owners by scripts/generate_wire.py. Do not edit.\n"
TOKEN_TUPLES: dict[str, type[StrEnum]] = {
    "SUIT_TOKENS": SuitToken,
    "RANK_TOKENS": RankToken,
    "POSITION_TOKENS": PositionToken,
    "GAME_TOKENS": GameToken,
    "ANNOUNCEMENT_TOKENS": AnnouncementToken,
    "STAGE_TOKENS": StageToken,
    "AWAITING_TOKENS": AwaitingToken,
    "AUCTION_ACTION_TOKENS": AuctionAction,
    "LEVEL_TOKENS": Level,
    "END_REASON_TOKENS": EndReason,
    "KONTRA_SAYER_TOKENS": KontraSayer,
    "KONTRA_REACH_TOKENS": KontraReach,
    "KONTRA_DEADLINE_TOKENS": KontraDeadline,
    "BOCK_TRIGGER_TOKENS": BockTrigger,
    "BOCK_OVERLAP_TOKENS": BockOverlap,
    "RAMSCH_OCCASION_TOKENS": RamschOccasion,
    "RAMSCH_SCORING_TOKENS": RamschScoring,
    "JUNGFRAU_TOKENS": JungfrauRule,
    "DURCHMARSCH_TOKENS": DurchmarschRule,
    "PUSHING_RULE_TOKENS": PushingRule,
    "GRAND_HAND_TOKENS": GrandHandRule,
    "WAITING_CASE_TOKENS": WaitingCase,
    "GAME_ENDING_TOKENS": GameEnding,
    "WORD_TOKENS": Word,
}


def token_tuple(name: str, tokens: type[StrEnum]) -> str:
    values = [f'"{token.value}"' for token in tokens]
    line = f"export const {name} = [{', '.join(values)}] as const;\n"
    if len(line.rstrip()) <= PRETTIER_WIDTH:
        return line
    stacked = "".join(f"    {value},\n" for value in values)
    return f"export const {name} = [\n{stacked}] as const;\n"


def literal(value: JsonValue, indent: int = 0) -> str:
    """A JSON value as the object literal prettier keeps: unquoted keys, objects over lines, arrays on one line."""
    inner = " " * (indent + 4)
    match value:
        case dict():
            members = "".join(f"{inner}{key}: {literal(each, indent + 4)},\n" for key, each in value.items())
            return "{\n" + members + " " * indent + "}"
        case list():
            return "[" + ", ".join(literal(each) for each in value) + "]"
        case _:
            return json.dumps(value)


def switch_on_options() -> str:
    """The start values of a rule switched on, in the answer's shape."""
    answer = options_answer_of(SWITCH_ON_OPTIONS).model_dump(mode="json")
    return f"export const SWITCH_ON_OPTIONS = {literal(answer)} as const;\n"


def path_constants() -> dict[str, str]:
    return {
        "AUTH_START_PATH": AUTH_START_PATH,
        "RETURN_PATH_QUERY_NAME": RETURN_PATH_QUERY_NAME,
        "SIGNED_IN_AGAIN_QUERY_NAME": SIGNED_IN_AGAIN_QUERY_NAME,
        "NO_ACCESS_PATH": NO_ACCESS_PATH,
        "MODE_QUERY_NAME": MODE_QUERY_NAME,
        "CALL_MODE": CALL_MODE,
        "LOGOUT_PATH": LOGOUT_PATH,
        "ACCOUNT_PATH": ACCOUNT_PATH,
        "VERSION_FILE_PATH": VERSION_FILE_PATH,
        "CALL_ORIGIN_PATH": CALL_ORIGIN_PATH,
        "ACCOUNT_CONSOLE_PATH": ACCOUNT_CONSOLE_PATH,
        "TABLES_PATH": TABLES_PATH,
        "RULE_SETS_PATH": RULE_SETS_PATH,
        "LOBBY_EVENTS_PATH": LOBBY_EVENTS_PATH,
        "TABLE_PAGE_PREFIX": TABLE_PAGE_PREFIX,
        "TABLE_ID_PATTERN": TABLE_ID_PATTERN,
        "TABLE_EVENTS_SUFFIX": TABLE_EVENTS_SUFFIX,
        "TABLE_SIT_SUFFIX": TABLE_SIT_SUFFIX,
        "TABLE_STAND_SUFFIX": TABLE_STAND_SUFFIX,
        "TABLE_DECLARING_TAKE_SUFFIX": TABLE_DECLARING_TAKE_SUFFIX,
        "TABLE_DECLARING_PUT_BACK_SUFFIX": TABLE_DECLARING_PUT_BACK_SUFFIX,
        "TABLE_DECLARING_DECLARE_SUFFIX": TABLE_DECLARING_DECLARE_SUFFIX,
        "TABLE_PUSHING_TAKE_SUFFIX": TABLE_PUSHING_TAKE_SUFFIX,
        "TABLE_PUSHING_PUT_BACK_SUFFIX": TABLE_PUSHING_PUT_BACK_SUFFIX,
        "TABLE_PUSHING_PUSH_SUFFIX": TABLE_PUSHING_PUSH_SUFFIX,
        "TABLE_PUSHING_GRAND_HAND_SUFFIX": TABLE_PUSHING_GRAND_HAND_SUFFIX,
        "TABLE_AUCTION_BID_SUFFIX": TABLE_AUCTION_BID_SUFFIX,
        "TABLE_AUCTION_HOLD_SUFFIX": TABLE_AUCTION_HOLD_SUFFIX,
        "TABLE_AUCTION_PASS_SUFFIX": TABLE_AUCTION_PASS_SUFFIX,
        "TABLE_AUCTION_PLAY_SUFFIX": TABLE_AUCTION_PLAY_SUFFIX,
        "TABLE_CARD_SUFFIX": TABLE_CARD_SUFFIX,
        "TABLE_GIVE_UP_SUFFIX": TABLE_GIVE_UP_SUFFIX,
        "TABLE_GIVE_UP_AGREE_SUFFIX": TABLE_GIVE_UP_AGREE_SUFFIX,
        "TABLE_GIVE_UP_DECLINE_SUFFIX": TABLE_GIVE_UP_DECLINE_SUFFIX,
        "TABLE_LIST_SUFFIX": TABLE_LIST_SUFFIX,
        "TABLE_KONTRA_SUFFIX": TABLE_KONTRA_SUFFIX,
        "TABLE_NO_WORD_SUFFIX": TABLE_NO_WORD_SUFFIX,
        "TABLE_READY_SUFFIX": TABLE_READY_SUFFIX,
        "TABLE_AGENTS_SUFFIX": TABLE_AGENTS_SUFFIX,
        "TABLE_AGENT_CALL_SUFFIX": TABLE_AGENT_CALL_SUFFIX,
        "TABLE_AGENT_SEND_AWAY_SUFFIX": TABLE_AGENT_SEND_AWAY_SUFFIX,
        "TABLE_ABORT_AGREE_SUFFIX": TABLE_ABORT_AGREE_SUFFIX,
        "TABLE_ABORT_REFUSE_SUFFIX": TABLE_ABORT_REFUSE_SUFFIX,
    }


def render() -> str:
    paths = "".join(f'export const {name} = "{path}";\n' for name, path in path_constants().items())
    tuples = "".join(token_tuple(name, tokens) for name, tokens in TOKEN_TUPLES.items())
    wrapped_bids = textwrap.fill(
        ", ".join(map(str, VALID_BIDS)) + ",", width=PRETTIER_WIDTH, initial_indent="    ", subsequent_indent="    "
    )
    valid_bids = f"export const VALID_BIDS = [\n{wrapped_bids}\n] as const;\n"
    all_points = f"export const ALL_POINTS = {ALL_POINTS};\n"
    series_length = "".join(
        f"export const {name} = {value};\n"
        for name, value in (
            ("SERIES_LENGTH_MIN", SERIES_LENGTH_MIN),
            ("SERIES_LENGTH_MAX", SERIES_LENGTH_MAX),
            ("SERIES_LENGTH_STEP", SERIES_LENGTH_STEP),
            ("SERIES_LENGTH_DEFAULT", SERIES_LENGTH_DEFAULT),
        )
    )
    chairs = f"export const CHAIRS_PER_TABLE = {CHAIRS_PER_TABLE};\n"
    return HEADER + "\n" + paths + tuples + valid_bids + all_points + series_length + chairs + switch_on_options()


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
