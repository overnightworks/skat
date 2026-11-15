"""A person at the table throws a reaction that every stream of the table shows: who may, how often and for how long.
A reaction changes nothing stored and moves no version.
"""

import pytest

from skat.table.reacting import REACTION_WINDOW_SECONDS, REACTIONS_PER_WINDOW, Reaction
from skat.web.reacting import TABLE_REACTION_SUFFIX
from skat.web.reaction_log import REACTION_SHOWN_SECONDS
from skat.web.tables import TABLES_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.playing import FOREHAND, MIDDLEHAND, REARHAND, Table
from tests.web.support.skat import UNKNOWN_ID, streams_of

# The chairs by name: Anna holds seat 1 (middlehand), Ben seat 2 and Cleo seat 3; Dora has none.
SEAT_OF = {"anna": 1, "ben": 2, "cleo": 3}


class Room:
    """A table of three people and a watcher with one open stream each, and a stranger who has the table closed."""

    def __init__(self, skat, time, table, streams):
        self.skat = skat
        self.time = time
        self.table = table
        self.streams = dict(zip(("anna", "ben", "cleo", "watcher"), streams, strict=True))
        self.headers = {"anna": table.at[MIDDLEHAND], "ben": table.at[REARHAND], "cleo": table.at[FOREHAND]}
        self.headers["watcher"] = table.watcher
        self.headers["stranger"] = skat.member()[0]

    def throw(self, who, reaction=Reaction.FIRE, *, table_id=None):
        self.skat.client.cookies.clear()
        return self.skat.client.post(
            f"{TABLES_PATH}/{table_id or self.table.table_id}{TABLE_REACTION_SUFFIX}",
            json={"reaction": str(reaction)},
            headers={"origin": TEST_PUBLIC_ORIGIN, **self.headers[who]},
        )

    def thrown(self, who, reaction=Reaction.FIRE):
        answer = self.throw(who, reaction)
        assert answer.status_code == 200, answer.text

    def reaching(self, who, number):
        """The first message of the person's stream that carries the reaction of that number."""
        return next(
            reaction
            for message in self.streams[who]
            for reaction in message["reactions"]
            if reaction["number"] == number
        )

    def read(self, who="anna"):
        answer = self.table.read_as(self.headers[who])
        assert answer.status_code == 200, answer.text
        return answer.json()

    def wait(self, seconds):
        self.skat.client.portal.call(self.time.advance, seconds)


@pytest.fixture
def room(server, time):
    table = Table(server)
    people = [(table.at[position], None) for position in (MIDDLEHAND, REARHAND, FOREHAND)]
    with streams_of(server, table.table_id, [*people, (table.watcher, None)]) as streams:
        yield Room(server, time, table, streams)


class TestWhoSeesWhatIsThrown:
    @pytest.mark.parametrize("who", ["anna", "ben", "cleo", "watcher"])
    def test_a_seated_persons_reaction_reaches_every_page_at_the_table_with_the_seat_and_the_name(self, room, who):
        room.thrown("ben", Reaction.CHEERS)

        assert room.reaching(who, 1) == {
            "number": 1,
            "reaction": "cheers",
            "by_seat": 2,
            "by_name": room.read()["chairs"][1]["occupant_name"],
        }

    @pytest.mark.parametrize("who", ["anna", "watcher"])
    def test_a_watchers_reaction_reaches_every_page_without_a_seat_and_without_a_name(self, room, who):
        room.thrown("watcher", Reaction.GASP)

        assert room.reaching(who, 1) == {"number": 1, "reaction": "gasp", "by_seat": None, "by_name": None}

    def test_each_throw_has_the_next_number_at_the_table(self, room):
        room.thrown("anna", Reaction.CLAP)
        room.thrown("cleo", Reaction.LAMP)

        assert [reaction["number"] for reaction in room.read()["reactions"]] == [1, 2]

    def test_a_reaction_moves_no_version(self, room):
        before = room.read()["version"]

        room.thrown("anna")

        assert room.read()["version"] == before

    def test_a_reaction_leaves_the_answer_once_it_has_been_shown_long_enough(self, room):
        room.thrown("anna")
        room.wait(REACTION_SHOWN_SECONDS)

        assert room.read()["reactions"] == []

    def test_a_table_that_was_never_thrown_at_has_none(self, room):
        assert room.read()["reactions"] == []

    def test_an_object_of_the_table_is_thrown_like_an_emote(self, room):
        room.thrown("watcher", Reaction.COCKTAIL)

        assert room.reaching("anna", 1)["reaction"] == "cocktail"


class TestWhoMayThrow:
    def test_a_stranger_who_neither_sits_nor_has_the_table_open_is_refused_and_nothing_is_shown(self, room):
        answer = room.throw("stranger")

        assert (answer.status_code, answer.json()["reason"], room.read()["reactions"]) == (409, "not-at-the-table", [])

    def test_a_table_nobody_has_is_not_found(self, room):
        assert room.throw("anna", table_id=UNKNOWN_ID).status_code == 404

    def test_a_reaction_outside_the_closed_set_is_refused_as_malformed(self, room):
        room.skat.client.cookies.clear()
        answer = room.skat.client.post(
            f"{TABLES_PATH}/{room.table.table_id}{TABLE_REACTION_SUFFIX}",
            json={"reaction": "poo"},
            headers={"origin": TEST_PUBLIC_ORIGIN, **room.headers["anna"]},
        )

        assert answer.status_code == 422


class TestHowOften:
    def test_a_person_past_the_limit_is_refused_with_its_own_code_and_throws_again_when_the_window_has_passed(
        self, room
    ):
        for _ in range(REACTIONS_PER_WINDOW):
            room.thrown("anna")

        refused = room.throw("anna")
        room.wait(REACTION_WINDOW_SECONDS)

        assert (refused.status_code, refused.json()["reason"], room.throw("anna").status_code) == (429, "too-fast", 200)

    def test_the_limit_is_each_persons_own(self, room):
        for _ in range(REACTIONS_PER_WINDOW):
            room.thrown("anna")

        assert room.throw("watcher").status_code == 200

    def test_a_refused_throw_shows_nothing(self, room):
        for _ in range(REACTIONS_PER_WINDOW):
            room.thrown("anna")
        room.throw("anna")

        assert len(room.read()["reactions"]) == REACTIONS_PER_WINDOW
