"""The lobby's event stream as a test serves it: whole lists the page takes as the stream's answer."""

from typing import TYPE_CHECKING

from skat.table.records import SERIES_LENGTH_DEFAULT, OccupantKind
from skat.web.lobby import LOBBY_EVENTS_PATH, OpenAnswer, OpenChairAnswer, OpenTableAnswer
from skat.web.table_options import GiveUpOptionsAnswer, OptionsAnswer

if TYPE_CHECKING:
    from datetime import datetime

    from playwright.sync_api import Page, Route

EVENT_STREAM = "text/event-stream"


def stream_event(name: str, answer: str) -> str:
    return f"event: {name}\ndata: {answer}\n\n"


def stream_of(*, mine: str = '{"tables":[]}', open_tables: list[OpenTableAnswer]) -> str:
    return stream_event("mine", mine) + stream_event("open", OpenAnswer(tables=open_tables).model_dump_json())


def serve_stream(person: Page, body: str) -> None:
    """The lobby stream answers the page with this body and ends, as a stream the network cuts does."""
    person.route(
        f"**{LOBBY_EVENTS_PATH}",
        lambda route: route.fulfill(status=200, headers={"content-type": EVENT_STREAM}, body=body),
    )


def open_table_answer(
    opener: str,
    *,
    options: OptionsAnswer | None = None,
    names: tuple[str | None, ...] = (None, None, None),
    away_hold: dict[int, int] | None = None,
    waiting_seat: int | None = None,
    ends_at: datetime | None = None,
) -> OpenTableAnswer:
    holds = away_hold or {}
    chairs = [
        OpenChairAnswer(
            seat=seat,
            occupant_name=name,
            occupant_kind=None if name is None else OccupantKind.PERSON,
            is_away=seat in holds,
            hold_seconds_left=holds.get(seat),
        )
        for seat, name in enumerate(names)
    ]
    return OpenTableAnswer(
        id=f"{ord(opener[0]):x}".ljust(32, "e"),
        title_name=opener,
        game_number=0,
        game_count=SERIES_LENGTH_DEFAULT,
        options=options
        or OptionsAnswer(
            show_running_points=False,
            kontra=None,
            bock=None,
            ramsch=None,
            give_up=GiveUpOptionsAnswer(partner_agrees=False, any_time=False),
        ),
        watchers=0,
        free_chairs=sum(name is None for name in names),
        dealt=ends_at is not None or waiting_seat is not None,
        waiting_seat=waiting_seat,
        ends_at=ends_at,
        chairs=chairs,
    )


def serve_streams_in_turn(person: Page, bodies: list[str]) -> None:
    """Each answer of the lobby stream is the next body, the last one for every later; each ends as a cut stream."""
    remaining = list(bodies)

    def answer(route: Route) -> None:
        body = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        route.fulfill(status=200, headers={"content-type": EVENT_STREAM}, body=body)

    person.route(f"**{LOBBY_EVENTS_PATH}", answer)
