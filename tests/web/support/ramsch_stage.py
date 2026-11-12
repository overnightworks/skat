from skat.engine.deal import positions_from
from skat.web.game_list import TABLE_LIST_SUFFIX
from skat.web.pushing import (
    TABLE_PUSHING_GRAND_HAND_SUFFIX,
    TABLE_PUSHING_PUSH_SUFFIX,
    TABLE_PUSHING_PUT_BACK_SUFFIX,
    TABLE_PUSHING_TAKE_SUFFIX,
)
from skat.web.tables import TABLES_PATH
from tests.support.payload_cards import DEALER_SEAT
from tests.web.support.playing import (
    FOREHAND,
    MIDDLEHAND,
    PLAIN_DEAL,
    REARHAND,
    Table,
    card_body,
    three_pass,
)

SEATS = {position: seat for seat, position in positions_from(DEALER_SEAT).items()}
FOREHAND_SEAT, MIDDLEHAND_SEAT, REARHAND_SEAT = SEATS[FOREHAND], SEATS[MIDDLEHAND], SEATS[REARHAND]
VIEWERS = (FOREHAND, MIDDLEHAND, REARHAND, None)
SUFFIXES = {
    "take": TABLE_PUSHING_TAKE_SUFFIX,
    "put-back": TABLE_PUSHING_PUT_BACK_SUFFIX,
    "push": TABLE_PUSHING_PUSH_SUFFIX,
    "grand-hand": TABLE_PUSHING_GRAND_HAND_SUFFIX,
}
POINTS = {"occasion": "passed-in", "scoring": "points", "jungfrau": "doubles-loser", "durchmarsch": "wins-120"}


def stage_table(skat, rule="jacks-stay", deal=PLAIN_DEAL, extra=None, grand_hand=None, **changed):
    """A Ramsch table whose hand all three passed, so its stage runs; `rule` None leaves pushing off and `grand_hand`
    names the Grand Hand the stage allows or leaves off.
    """
    allowed = {} if grand_hand is None else {"grand_hand": grand_hand}
    pushing = {} if rule is None else {"pushing": {"rule": rule, **allowed}}
    table = Table(skat, {"ramsch": {**POINTS, **changed, **pushing}, **(extra or {})})
    table.with_deal(deal)
    three_pass(table)
    return table


def read(table, position=None):
    headers = table.watcher if position is None else table.at[position]
    return table.read_as(headers).json()


def step_body(put):
    return {"cards": [card_body(each) for each in put]} if put else None


def step(table, position, kind, put=()):
    return table.act(SUFFIXES[kind], table.at[position], body=step_body(put))


def accepted(table, position, kind, put=()):
    before = table.record.version
    answer = step(table, position, kind, put)
    assert answer.status_code == 200, answer.text
    assert table.record.version == before + 1
    return answer.json()


def refused(table, position, kind, reason, put=()):
    table.refused_act(SUFFIXES[kind], table.at[position], reason, body=step_body(put))


def play_stage(table, *plan):
    """Each seat in turn pushes the skat on ("push") or takes it and puts the very cards back ("back"); fewer than three
    choices leave the stage running at the next seat.
    """
    skat_cards = table.record.hand.skat
    for position, choice in zip((FOREHAND, MIDDLEHAND, REARHAND), plan, strict=len(plan) == 3):
        if choice == "push":
            accepted(table, position, "push")
        else:
            accepted(table, position, "take")
            accepted(table, position, "put-back", skat_cards)


def list_rows(table):
    table.skat.client.cookies.clear()
    answer = table.skat.client.get(f"{TABLES_PATH}/{table.table_id}{TABLE_LIST_SUFFIX}", headers=table.watcher)
    assert answer.status_code == 200, answer.text
    return answer.json()["entries"]
