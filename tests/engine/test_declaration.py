import pytest

from skat.engine.bidding import Declared
from skat.engine.cards import DECK, Card, Rank, Suit
from skat.engine.deal import Deal, Position
from skat.engine.declaration import (
    Announcement,
    Declaration,
    DeclarationOutcome,
    DeclarationRefusal,
    Declare,
    DeclaringStep,
    Declaring,
    PutBack,
    TakeSkat,
    declare,
    declaring_after,
    declaring_step,
    put_back,
    take_skat,
)
from skat.engine.games import GameKind, NullLevels

KARO_SEVEN = Card(Suit.KARO, Rank.SEVEN)
HERZ_EIGHT = Card(Suit.HERZ, Rank.EIGHT)
PIK_KING = Card(Suit.PIK, Rank.KING)
BID = 30
NONE, SCHNEIDER, SCHWARZ = Announcement.NONE, Announcement.SCHNEIDER, Announcement.SCHWARZ
HERZ, GRAND, NULL, KREUZ = GameKind.HERZ, GameKind.GRAND, GameKind.NULL, GameKind.KREUZ
NOT_TWO = DeclarationRefusal.NOT_TWO_OF_THE_TWELVE
OUT_OF_ORDER = DeclarationRefusal.OUT_OF_ORDER
AFTER_PICK_UP = DeclarationRefusal.LEVEL_NOT_ALLOWED_AFTER_PICK_UP
IN_NULL = DeclarationRefusal.ANNOUNCEMENT_IN_NULL
ALREADY = DeclarationRefusal.ALREADY_DECLARED


def fresh() -> Declaring:
    others = [card for card in DECK if card not in {KARO_SEVEN, PIK_KING, HERZ_EIGHT}]
    hand = (HERZ_EIGHT, *others[:9])
    skat = (KARO_SEVEN, PIK_KING)
    rest = tuple(others[9:])
    deal = Deal(forehand=hand, middlehand=rest[:10], rearhand=rest[10:20], skat=skat)
    return Declaring.start(Declared(Position.FOREHAND, BID), deal)


def picked() -> Declaring:
    state = take_skat(fresh()).state
    return put_back(state, (KARO_SEVEN, HERZ_EIGHT)).state


def ok(outcome: DeclarationOutcome) -> Declaring:
    assert outcome.refusal is None
    return outcome.state


def refused(outcome: DeclarationOutcome, reason: DeclarationRefusal, before: Declaring) -> None:
    assert outcome.refusal is reason
    assert outcome.state == before


def declared_hand(kind: GameKind = HERZ, ouvert: bool = False, announcement: Announcement = NONE) -> Declaring:
    return ok(declare(fresh(), kind, hand=True, ouvert=ouvert, announcement=announcement))


def test_taking_the_skat_gives_twelve_cards_and_puts_back_two_to_leave_ten() -> None:
    state = ok(take_skat(fresh()))
    assert len(state.hand) == 12
    assert {KARO_SEVEN, PIK_KING} <= set(state.hand)
    state = ok(put_back(state, (KARO_SEVEN, HERZ_EIGHT)))
    assert len(state.hand) == 10
    assert KARO_SEVEN not in state.hand
    assert HERZ_EIGHT not in state.hand
    assert PIK_KING in state.hand
    assert set(state.skat) == {KARO_SEVEN, HERZ_EIGHT}
    assert len(state.skat) == 2


@pytest.mark.parametrize(
    "cards",
    [
        (KARO_SEVEN,),
        (KARO_SEVEN, HERZ_EIGHT, PIK_KING),
        (KARO_SEVEN, Card(Suit.KARO, Rank.ACE)),
        (KARO_SEVEN, KARO_SEVEN),
        (),
    ],
)
def test_putting_back_anything_but_two_of_the_twelve_is_refused(cards: tuple[Card, ...]) -> None:
    state = ok(take_skat(fresh()))
    refused(put_back(state, cards), NOT_TWO, state)


def test_a_hand_game_leaves_the_skat_untouched() -> None:
    before = fresh()
    state = ok(declare(before, HERZ, hand=True, ouvert=False, announcement=NONE))
    assert state.skat == before.skat
    assert state.hand == before.hand
    assert state.declaration == Declaration(HERZ, hand=True, ouvert=False, announcement=NONE)


@pytest.mark.parametrize(
    ("kind", "hand", "ouvert", "announcement"),
    [
        (HERZ, True, False, NONE),
        (HERZ, False, False, SCHNEIDER),
        (HERZ, False, True, NONE),
        (GRAND, False, True, SCHWARZ),
        (HERZ, False, False, SCHWARZ),
        (NULL, True, False, NONE),
        (NULL, False, False, SCHNEIDER),
    ],
)
def test_after_pick_up_hand_announcements_and_ouvert_games_are_refused(
    kind: GameKind, hand: bool, ouvert: bool, announcement: Announcement
) -> None:
    before = picked()
    refused(declare(before, kind, hand=hand, ouvert=ouvert, announcement=announcement), AFTER_PICK_UP, before)


@pytest.mark.parametrize(
    ("kind", "ouvert"),
    [(HERZ, False), (GRAND, False), (NULL, False), (NULL, True), (GameKind.KARO, False), (GameKind.PIK, False)],
)
def test_after_pick_up_a_suit_grand_null_or_null_ouvert_game_is_accepted(kind: GameKind, ouvert: bool) -> None:
    state = ok(declare(picked(), kind, hand=False, ouvert=ouvert, announcement=NONE))
    assert state.declaration == Declaration(kind, hand=False, ouvert=ouvert, announcement=NONE)


@pytest.mark.parametrize(
    ("kind", "ouvert", "announcement"),
    [
        (KREUZ, False, SCHNEIDER),
        (KREUZ, False, SCHWARZ),
        (HERZ, False, NONE),
        (GRAND, True, SCHWARZ),
        (NULL, False, NONE),
        (NULL, True, NONE),
    ],
)
def test_without_pick_up_hand_games_with_their_levels_are_accepted(
    kind: GameKind, ouvert: bool, announcement: Announcement
) -> None:
    state = declared_hand(kind, ouvert, announcement)
    assert state.declaration is not None
    assert state.declaration.hand


def test_a_null_game_cannot_be_announced_schneider() -> None:
    before = fresh()
    refused(declare(before, NULL, hand=True, ouvert=False, announcement=SCHNEIDER), IN_NULL, before)


def test_an_announcement_without_hand_and_without_pick_up_is_out_of_order() -> None:
    before = fresh()
    refused(declare(before, HERZ, hand=False, ouvert=False, announcement=SCHNEIDER), OUT_OF_ORDER, before)


def test_an_announcement_after_pick_up_is_a_level_not_allowed() -> None:
    before = picked()
    refused(declare(before, HERZ, hand=False, ouvert=False, announcement=SCHNEIDER), AFTER_PICK_UP, before)


@pytest.mark.parametrize("kind", [KREUZ, GRAND])
@pytest.mark.parametrize("announced", list(Announcement))
def test_an_ouvert_suit_or_grand_game_is_a_hand_game_announced_schwarz(kind: GameKind, announced: Announcement) -> None:
    declaration = declared_hand(kind, ouvert=True, announcement=announced).declaration
    assert declaration == Declaration(kind, hand=True, ouvert=True, announcement=SCHWARZ)


def test_ouvert_without_hand_and_without_pick_up_is_out_of_order() -> None:
    before = fresh()
    refused(declare(before, KREUZ, hand=False, ouvert=True, announcement=NONE), OUT_OF_ORDER, before)


def test_a_second_or_changed_declaration_is_refused() -> None:
    before = declared_hand(HERZ)
    for kind in (HERZ, GRAND):
        refused(declare(before, kind, hand=True, ouvert=False, announcement=NONE), ALREADY, before)


@pytest.mark.parametrize("kind", [GameKind.KARO, NULL])
def test_a_game_below_the_bid_is_accepted(kind: GameKind) -> None:
    state = ok(declare(picked(), kind, hand=False, ouvert=False, announcement=NONE))
    assert state.bid == BID
    assert state.declaration is not None
    assert state.declaration.kind is kind


def test_without_pick_up_a_declaration_without_hand_is_out_of_order() -> None:
    before = fresh()
    refused(declare(before, HERZ, hand=False, ouvert=False, announcement=NONE), OUT_OF_ORDER, before)


@pytest.mark.parametrize(
    ("start", "action"),
    [
        pytest.param(fresh, lambda state: put_back(state, (KARO_SEVEN, HERZ_EIGHT)), id="put-back-before-taking"),
        pytest.param(picked, lambda state: put_back(state, (KARO_SEVEN, HERZ_EIGHT)), id="put-back-twice"),
        pytest.param(picked, take_skat, id="take-after-put-back"),
    ],
)
def test_actions_out_of_order_are_refused(start, action) -> None:
    before = start()
    refused(action(before), OUT_OF_ORDER, before)


def test_declaring_before_putting_back_after_pick_up_is_out_of_order() -> None:
    before = ok(take_skat(fresh()))
    refused(declare(before, HERZ, hand=False, ouvert=False, announcement=NONE), OUT_OF_ORDER, before)


def test_take_skat_twice_leaves_the_state_unchanged() -> None:
    before = ok(take_skat(fresh()))
    refused(take_skat(before), OUT_OF_ORDER, before)


def test_nothing_changes_after_the_declaration() -> None:
    before = declared_hand(HERZ)
    refused(take_skat(before), ALREADY, before)
    refused(put_back(before, (KARO_SEVEN, HERZ_EIGHT)), ALREADY, before)
    refused(declare(before, HERZ, hand=True, ouvert=False, announcement=NONE), ALREADY, before)


@pytest.mark.parametrize(
    ("hand", "ouvert", "levels"),
    [
        (False, False, NullLevels(hand=False, ouvert=False)),
        (True, False, NullLevels(hand=True, ouvert=False)),
        (False, True, NullLevels(hand=False, ouvert=True)),
        (True, True, NullLevels(hand=True, ouvert=True)),
    ],
)
def test_null_declarations_map_to_the_null_levels_key(hand: bool, ouvert: bool, levels: NullLevels) -> None:
    assert Declaration(NULL, hand=hand, ouvert=ouvert, announcement=NONE).null_levels == levels


def test_a_suit_game_has_no_null_levels_key() -> None:
    assert Declaration(HERZ, hand=False, ouvert=False, announcement=NONE).null_levels is None


def test_the_ended_state_after_pick_up_holds_declarer_bid_ten_cards_skat_and_declaration() -> None:
    state = ok(declare(picked(), HERZ, hand=False, ouvert=False, announcement=NONE))
    assert state.declarer is Position.FOREHAND
    assert state.bid == BID
    assert len(state.hand) == 10
    assert set(state.skat) == {KARO_SEVEN, HERZ_EIGHT}
    assert state.declaration == Declaration(HERZ, hand=False, ouvert=False, announcement=NONE)


def test_the_ended_state_after_hand_holds_ten_cards_and_the_untouched_skat() -> None:
    start = fresh()
    state = declared_hand(GRAND)
    assert state.declarer is Position.FOREHAND
    assert state.bid == BID
    assert state.hand == start.hand
    assert state.skat == start.skat
    assert state.declaration == Declaration(GRAND, hand=True, ouvert=False, announcement=NONE)


@pytest.mark.parametrize(
    ("kind", "hand", "ouvert", "announcement"),
    [
        (HERZ, False, False, SCHNEIDER),
        (HERZ, False, False, SCHWARZ),
        (GRAND, False, False, SCHNEIDER),
        (NULL, True, False, SCHNEIDER),
        (NULL, False, False, SCHWARZ),
        (HERZ, False, True, SCHWARZ),
        (HERZ, True, True, NONE),
        (HERZ, True, True, SCHNEIDER),
        (GRAND, True, True, NONE),
    ],
)
def test_a_declaration_with_an_impossible_combination_is_a_programming_fault(
    kind: GameKind, hand: bool, ouvert: bool, announcement: Announcement
) -> None:
    with pytest.raises(ValueError, match="impossible"):
        Declaration(kind, hand=hand, ouvert=ouvert, announcement=announcement)


def declare_hand_step() -> Declare:
    return Declare(HERZ, hand=True, ouvert=False, announcement=NONE)


def test_an_empty_declaring_log_replays_to_the_start_state() -> None:
    assert declaring_after(fresh(), ()) == fresh()


def test_a_declaring_log_replays_to_what_the_direct_calls_give() -> None:
    steps = (TakeSkat(), PutBack((KARO_SEVEN, HERZ_EIGHT)), Declare(HERZ, hand=False, ouvert=False, announcement=NONE))
    direct = ok(declare(picked(), HERZ, hand=False, ouvert=False, announcement=NONE))
    assert declaring_after(fresh(), steps) == direct


def test_a_hand_declaration_without_taking_replays_to_the_direct_call() -> None:
    direct = declared_hand()
    assert declaring_after(fresh(), (declare_hand_step(),)) == direct


@pytest.mark.parametrize(
    ("steps", "reason", "place"),
    [
        ((PutBack((KARO_SEVEN, HERZ_EIGHT)),), OUT_OF_ORDER, "step 1"),
        ((TakeSkat(), PutBack((KARO_SEVEN, Card(Suit.KARO, Rank.ACE)))), NOT_TWO, "step 2"),
        ((declare_hand_step(), declare_hand_step()), ALREADY, "step 2"),
    ],
)
def test_a_declaring_log_the_rules_refuse_raises_naming_the_refusal_and_the_place(
    steps: tuple[DeclaringStep, ...], reason: DeclarationRefusal, place: str
) -> None:
    with pytest.raises(ValueError, match=f"{place}.*{reason.value}"):
        declaring_after(fresh(), steps)


@pytest.mark.parametrize(
    "step",
    [TakeSkat(), PutBack((KARO_SEVEN, HERZ_EIGHT)), declare_hand_step()],
)
@pytest.mark.parametrize("state", [fresh(), picked(), declared_hand()])
def test_a_declaring_step_gives_the_outcome_of_the_direct_function_and_a_refusal_changes_nothing(
    state: Declaring, step: DeclaringStep
) -> None:
    if isinstance(step, TakeSkat):
        direct = take_skat(state)
    elif isinstance(step, PutBack):
        direct = put_back(state, step.cards)
    else:
        direct = declare(state, step.kind, hand=step.hand, ouvert=step.ouvert, announcement=step.announcement)
    outcome = declaring_step(state, step)
    assert outcome == direct
    if outcome.refusal is not None:
        assert outcome.state == state
