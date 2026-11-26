"""Write the browser's typed copy of the paths, answer tokens and table answers the Python app owns.

The Python constants own the paths, the enums own the tokens and the pydantic models own the table's answers; this
generator renders them as TypeScript constants and types.
`--check` writes nothing and fails when the committed file differs from the rendering or is
missing, so CI catches drift.
"""

import json
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic.json_schema import GenerateJsonSchema

PRETTIER_WIDTH = 120  # the width prettier wraps the generated array at
REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "src"))

from skat.engine.bidding import VALID_BIDS, BidRefusal  # noqa: E402
from skat.engine.bock import BockOverlap, BockTrigger  # noqa: E402
from skat.engine.declaration import DeclarationRefusal  # noqa: E402
from skat.engine.kontra import KontraDeadline, KontraReach, KontraRefusal, KontraSayer, Word  # noqa: E402
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschScoring  # noqa: E402
from skat.engine.schieberamsch import GrandHandRule, PushingRule, PushRefusal  # noqa: E402
from skat.engine.tricks import ALL_POINTS, PlayRefusal  # noqa: E402
from skat.engine.value import Level  # noqa: E402
from skat.table.asking import ASK_AGAIN_AFTER  # noqa: E402
from skat.table.auction import AuctionAction  # noqa: E402
from skat.table.awaiting import WaitingCase  # noqa: E402
from skat.table.game_list import GameEnding  # noqa: E402
from skat.table.game_sheet import CardState  # noqa: E402
from skat.table.nudging import NudgeRefusal  # noqa: E402
from skat.table.pushing import PushAction  # noqa: E402
from skat.table.reacting import Reaction, ReactionRefusal  # noqa: E402
from skat.table.records import (  # noqa: E402
    SERIES_LENGTH_DEFAULT,
    SERIES_LENGTH_MAX,
    SERIES_LENGTH_MIN,
    SERIES_LENGTH_STEP,
    TABLE_ID_PATTERN,
    EndReason,
    OccupantKind,
    PlanMode,
    RamschOccasion,
    Refusal,
    TableStyle,
    Visibility,
)
from skat.table.rule_sets import RULE_SET_NAME_MAX, SWITCH_ON_OPTIONS, RuleSetRefusal  # noqa: E402
from skat.table.rules import CHAIRS_PER_TABLE  # noqa: E402
from skat.web.abort import TABLE_ABORT_AGREE_SUFFIX, TABLE_ABORT_REFUSE_SUFFIX  # noqa: E402
from skat.web.account import AccountName  # noqa: E402
from skat.web.auction import (  # noqa: E402
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAN_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
)
from skat.web.call import CALL_ORIGIN_PATH, CallOrigin  # noqa: E402
from skat.web.calling import TABLE_AGENT_CALL_SUFFIX, TABLE_AGENT_SEND_AWAY_SUFFIX, TABLE_AGENTS_SUFFIX  # noqa: E402
from skat.web.constants import (  # noqa: E402
    ACCOUNT_CONSOLE_PATH,
    ACCOUNT_PATH,
    AUTH_START_PATH,
    CALL_MODE,
    CALL_SIGN_IN_PATH,
    LOGOUT_PATH,
    MODE_QUERY_NAME,
    NO_ACCESS_PATH,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
    STREAM_HEARTBEAT_SECONDS,
    VERSION_FILE_PATH,
)
from skat.web.declaration_tokens import AnnouncementToken, GameToken  # noqa: E402
from skat.web.declaring import (  # noqa: E402
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
)
from skat.web.game_list import TABLE_LIST_SUFFIX, GameSheetAnswer, SeriesListAnswer  # noqa: E402
from skat.web.kontra import TABLE_KONTRA_SUFFIX, TABLE_NO_WORD_SUFFIX  # noqa: E402
from skat.web.lobby import LOBBY_EVENTS_PATH, MineAnswer, OpenAnswer  # noqa: E402
from skat.web.nudging import TABLE_NUDGE_SUFFIX  # noqa: E402
from skat.web.playing import (  # noqa: E402
    TABLE_CARD_SUFFIX,
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_PLAY_OPEN_SUFFIX,
    TABLE_SHORTEN_SUFFIX,
)
from skat.web.pushing import (  # noqa: E402
    TABLE_PUSHING_GRAND_HAND_SUFFIX,
    TABLE_PUSHING_PUSH_SUFFIX,
    TABLE_PUSHING_PUT_BACK_SUFFIX,
    TABLE_PUSHING_TAKE_SUFFIX,
)
from skat.web.reacting import TABLE_REACTION_SUFFIX  # noqa: E402
from skat.web.ready import TABLE_NEW_SERIES_SUFFIX, TABLE_NEXT_SETTINGS_SUFFIX, TABLE_READY_SUFFIX  # noqa: E402
from skat.web.rule_sets import RULE_SETS_PATH, RuleSetRefusalAnswer, RuleSetsAnswer  # noqa: E402
from skat.web.series_end import TABLE_SERIES_END_AGREE_SUFFIX, TABLE_SERIES_END_REFUSE_SUFFIX  # noqa: E402
from skat.web.stopping import TABLE_STOP_PLAYING_SUFFIX  # noqa: E402
from skat.web.style import TABLE_STYLE_SUFFIX  # noqa: E402
from skat.web.table_options import options_answer_of  # noqa: E402
from skat.web.table_tokens import (  # noqa: E402
    AwaitingToken,
    PositionToken,
    RankToken,
    StageToken,
    SuitToken,
)
from skat.web.tables import (  # noqa: E402
    TABLE_EVENTS_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
    PlanKind,
    RefusalAnswer,
    TableAnswer,
)
from skat.web.turn_state_answer import StopOutcome  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence
    from enum import StrEnum

    from pydantic import BaseModel, JsonValue
    from pydantic.json_schema import JsonSchemaValue
    from pydantic_core import core_schema

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
    "PLAN_KIND_TOKENS": PlanKind,
    "PLAN_MODE_TOKENS": PlanMode,
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
    "VISIBILITY_TOKENS": Visibility,
    "TABLE_STYLE_TOKENS": TableStyle,
    "REACTION_TOKENS": Reaction,
    "OCCUPANT_KIND_TOKENS": OccupantKind,
    "STOP_OUTCOME_TOKENS": StopOutcome,
    "PUSH_ACTION_TOKENS": PushAction,
    "CARD_STATE_TOKENS": CardState,
    "RULE_SET_REFUSAL_TOKENS": RuleSetRefusal,
    "REFUSAL_TOKENS": Refusal,
    "BID_REFUSAL_TOKENS": BidRefusal,
    "DECLARATION_REFUSAL_TOKENS": DeclarationRefusal,
    "PLAY_REFUSAL_TOKENS": PlayRefusal,
    "KONTRA_REFUSAL_TOKENS": KontraRefusal,
    "PUSH_REFUSAL_TOKENS": PushRefusal,
    "NUDGE_REFUSAL_TOKENS": NudgeRefusal,
    "REACTION_REFUSAL_TOKENS": ReactionRefusal,
}
ANSWER_ROOTS = (
    TableAnswer,
    MineAnswer,
    OpenAnswer,
    SeriesListAnswer,
    GameSheetAnswer,
    RuleSetsAnswer,
    RuleSetRefusalAnswer,
    AccountName,
    CallOrigin,
    RefusalAnswer,
)
ENUM_TUPLES = {tokens.__name__: name for name, tokens in TOKEN_TUPLES.items()}
SCALAR_TYPES = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}


class EveryPropertyRequired(GenerateJsonSchema):
    """The server serializes every field of an answer, so every property of every model the page reads is required."""

    def model_schema(self, schema: core_schema.ModelSchema) -> JsonSchemaValue:
        json_schema = super().model_schema(schema)
        json_schema["required"] = list(json_schema.get("properties", {}))
        return json_schema


def token_tuple(name: str, tokens: type[StrEnum]) -> str:
    values = [f'"{token.value}"' for token in tokens]
    line = f"export const {name} = [{', '.join(values)}] as const;\n"
    if len(line.rstrip()) <= PRETTIER_WIDTH:
        return line
    stacked = "".join(f"    {value},\n" for value in values)
    return f"export const {name} = [\n{stacked}] as const;\n"


def reference_type(node: JsonSchemaValue, definitions: JsonSchemaValue, enum_tuples: Mapping[str, str]) -> str:
    name = node["$ref"].rsplit("/", 1)[-1]
    if "enum" not in definitions[name]:
        return name
    if name not in enum_tuples:
        raise ValueError(f"generate_wire: enum {name} has no token tuple")
    return f"(typeof {enum_tuples[name]})[number]"


def union_members(node: JsonSchemaValue, definitions: JsonSchemaValue, enum_tuples: Mapping[str, str]) -> list[str]:
    """The types a union node is one of, or none for a node that is no union."""
    members: list[JsonSchemaValue] = node.get("anyOf") or (node.get("oneOf") if "discriminator" in node else None) or []
    return [type_of(member, definitions, enum_tuples) for member in members]


def type_of(node: JsonSchemaValue, definitions: JsonSchemaValue, enum_tuples: Mapping[str, str]) -> str:
    """A JSON schema node as a TypeScript type; a construct the answers do not use fails loudly."""
    if "$ref" in node:
        return reference_type(node, definitions, enum_tuples)
    if "const" in node:
        return json.dumps(node["const"])
    if members := union_members(node, definitions, enum_tuples):
        return " | ".join(members)
    if node.get("type") == "array":
        if "items" not in node:
            raise ValueError(f"generate_wire: no TypeScript for {node}")
        item = type_of(node["items"], definitions, enum_tuples)
        return f"({item})[]" if {"anyOf", "oneOf"} & node["items"].keys() else f"{item}[]"
    if node.get("type") in SCALAR_TYPES and "enum" not in node:
        return SCALAR_TYPES[node["type"]]
    raise ValueError(f"generate_wire: no TypeScript for {node}")


def member_line(
    key: str, is_required: bool, node: JsonSchemaValue, definitions: JsonSchemaValue, enum_tuples: Mapping[str, str]
) -> str:
    """A member of a model; a union too long for one line stacks its types as prettier does."""
    name = f"{key}{'' if is_required else '?'}"
    line = f"    {name}: {type_of(node, definitions, enum_tuples)};\n"
    if len(line.rstrip()) <= PRETTIER_WIDTH or not (members := union_members(node, definitions, enum_tuples)):
        return line
    stacked = "".join(f"        | {member}\n" for member in members)
    return f"    {name}:\n{stacked[:-1]};\n"


def alias_type(name: str, node: JsonSchemaValue, definitions: JsonSchemaValue, enum_tuples: Mapping[str, str]) -> str:
    """A union of enums the server names as one type, as a type alias; prettier stacks one too long for a line."""
    if not (members := union_members(node, definitions, enum_tuples)):
        raise ValueError(f"generate_wire: no TypeScript for {name}")
    line = f"export type {name} = {' | '.join(members)};\n"
    if len(line.rstrip()) <= PRETTIER_WIDTH:
        return line
    stacked = "".join(f"    | {member}\n" for member in members)
    return f"export type {name} =\n{stacked[:-1]};\n"


def model_type(name: str, model: JsonSchemaValue, definitions: JsonSchemaValue, enum_tuples: Mapping[str, str]) -> str:
    if "properties" not in model:
        return alias_type(name, model, definitions, enum_tuples)
    required = model.get("required", [])
    members = "".join(
        member_line(key, key in required, node, definitions, enum_tuples) for key, node in model["properties"].items()
    )
    return f"export type {name} = {{\n{members}}};\n"


def reached_models(core_schema_node: object) -> Iterator[type[BaseModel]]:
    """The model classes a pydantic core schema reaches."""
    children: Iterable[object] = ()
    if isinstance(core_schema_node, dict):
        mapping = cast("dict[str, object]", core_schema_node)
        if mapping.get("type") == "model":
            yield cast("type[BaseModel]", mapping["cls"])
        children = mapping.values()
    elif isinstance(core_schema_node, list):
        children = cast("list[object]", core_schema_node)
    for each in children:
        yield from reached_models(each)


def require_one_model_per_name(roots: Sequence[type[BaseModel]]) -> None:
    """The page names a type by its class name, so two models of one name would overwrite each other."""
    owners: dict[str, set[type[BaseModel]]] = {}
    for root in roots:
        for model in reached_models(root.__pydantic_core_schema__):
            owners.setdefault(model.__name__, set()).add(model)
    for name, models in owners.items():
        if len(models) > 1:
            modules = " and ".join(sorted(model.__module__ for model in models))
            raise ValueError(f"generate_wire: two models are named {name}: {modules}")


def answer_types(roots: Sequence[type[BaseModel]], enum_tuples: Mapping[str, str]) -> str:
    """Every model the roots reach as an exported type named after it, once; an enum as the union of its token tuple."""
    require_one_model_per_name(roots)
    models: dict[str, JsonSchemaValue] = {}
    definitions: dict[str, JsonSchemaValue] = {}
    for root in roots:
        schema = root.model_json_schema(mode="serialization", schema_generator=EveryPropertyRequired)
        definitions |= schema.pop("$defs", {})
        models[schema["title"]] = schema
    models |= {name: each for name, each in definitions.items() if "enum" not in each}
    return "".join(model_type(name, models[name], definitions, enum_tuples) for name in sorted(models))


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
        "CALL_SIGN_IN_PATH": CALL_SIGN_IN_PATH,
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
        "TABLE_STOP_PLAYING_SUFFIX": TABLE_STOP_PLAYING_SUFFIX,
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
        "TABLE_AUCTION_PLAN_SUFFIX": TABLE_AUCTION_PLAN_SUFFIX,
        "TABLE_AUCTION_PLAY_SUFFIX": TABLE_AUCTION_PLAY_SUFFIX,
        "TABLE_CARD_SUFFIX": TABLE_CARD_SUFFIX,
        "TABLE_GIVE_UP_SUFFIX": TABLE_GIVE_UP_SUFFIX,
        "TABLE_GIVE_UP_AGREE_SUFFIX": TABLE_GIVE_UP_AGREE_SUFFIX,
        "TABLE_GIVE_UP_DECLINE_SUFFIX": TABLE_GIVE_UP_DECLINE_SUFFIX,
        "TABLE_SHORTEN_SUFFIX": TABLE_SHORTEN_SUFFIX,
        "TABLE_PLAY_OPEN_SUFFIX": TABLE_PLAY_OPEN_SUFFIX,
        "TABLE_LIST_SUFFIX": TABLE_LIST_SUFFIX,
        "TABLE_KONTRA_SUFFIX": TABLE_KONTRA_SUFFIX,
        "TABLE_NO_WORD_SUFFIX": TABLE_NO_WORD_SUFFIX,
        "TABLE_READY_SUFFIX": TABLE_READY_SUFFIX,
        "TABLE_NEW_SERIES_SUFFIX": TABLE_NEW_SERIES_SUFFIX,
        "TABLE_NEXT_SETTINGS_SUFFIX": TABLE_NEXT_SETTINGS_SUFFIX,
        "TABLE_STYLE_SUFFIX": TABLE_STYLE_SUFFIX,
        "TABLE_SERIES_END_AGREE_SUFFIX": TABLE_SERIES_END_AGREE_SUFFIX,
        "TABLE_SERIES_END_REFUSE_SUFFIX": TABLE_SERIES_END_REFUSE_SUFFIX,
        "TABLE_AGENTS_SUFFIX": TABLE_AGENTS_SUFFIX,
        "TABLE_AGENT_CALL_SUFFIX": TABLE_AGENT_CALL_SUFFIX,
        "TABLE_AGENT_SEND_AWAY_SUFFIX": TABLE_AGENT_SEND_AWAY_SUFFIX,
        "TABLE_ABORT_AGREE_SUFFIX": TABLE_ABORT_AGREE_SUFFIX,
        "TABLE_ABORT_REFUSE_SUFFIX": TABLE_ABORT_REFUSE_SUFFIX,
        "TABLE_NUDGE_SUFFIX": TABLE_NUDGE_SUFFIX,
        "TABLE_REACTION_SUFFIX": TABLE_REACTION_SUFFIX,
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
    ask_again_after = f"export const ASK_AGAIN_AFTER = {ASK_AGAIN_AFTER:g};\n"
    rule_set_name_max = f"export const RULE_SET_NAME_MAX = {RULE_SET_NAME_MAX};\n"
    stream_heartbeat = f"export const STREAM_HEARTBEAT_SECONDS = {STREAM_HEARTBEAT_SECONDS};\n"
    return (
        HEADER
        + "\n"
        + paths
        + tuples
        + valid_bids
        + all_points
        + series_length
        + chairs
        + ask_again_after
        + rule_set_name_max
        + stream_heartbeat
        + switch_on_options()
        + answer_types(ANSWER_ROOTS, ENUM_TUPLES)
    )


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
