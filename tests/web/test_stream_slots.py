import gc

import pytest
from fastapi import HTTPException

from skat.web.lobby import LOBBY_EVENTS_PATH
from skat.web.streams import StreamSlots, event_stream_response
from skat.web.tables import TABLE_EVENTS_SUFFIX, TABLES_PATH
from tests.web.support.skat import UNKNOWN_ID, Skat
from tests.web.support.streams import run_on_a_loop_of_its_own


class TestStreamSlots:
    def test_an_account_takes_slots_up_to_its_limit_and_the_next_is_refused_with_429(self):
        slots = StreamSlots(2)
        slots.take("account-a")
        slots.take("account-a")

        with pytest.raises(HTTPException) as refused:
            slots.take("account-a")

        assert refused.value.status_code == 429

    def test_another_account_has_slots_of_its_own(self):
        slots = StreamSlots(1)
        slots.take("account-a")

        slots.take("account-b")

    def test_a_released_slot_is_free_again_and_releasing_it_twice_frees_only_that_one(self):
        slots = StreamSlots(2)
        release = slots.take("account-a")
        slots.take("account-a")
        release()
        release()
        slots.take("account-a")

        with pytest.raises(HTTPException):
            slots.take("account-a")

    def test_a_stream_that_ends_gives_its_slot_back(self):
        slots = StreamSlots(1)
        release = slots.take("account-a")

        async def messages():
            yield "data: one\n\n"

        async def scenario():
            response = event_stream_response(messages(), release)
            return [message async for message in response.body_iterator]

        run_on_a_loop_of_its_own(scenario())

        slots.take("account-a")

    def test_a_stream_whose_producer_fails_passes_the_error_on_and_gives_its_slot_back_at_once(self):
        slots = StreamSlots(1)

        async def messages():
            yield "data: one\n\n"
            message = "the producer failed"
            raise RuntimeError(message)

        async def scenario():
            response = event_stream_response(messages(), slots.take("account-a"))
            with pytest.raises(RuntimeError, match="the producer failed"):
                _ = [message async for message in response.body_iterator]
            return response

        response = run_on_a_loop_of_its_own(scenario())

        slots.take("account-a")
        assert response is not None

    def test_a_response_dropped_before_its_first_message_gives_its_slot_back(self):
        slots = StreamSlots(1)

        async def messages():
            yield "data: one\n\n"

        event_stream_response(messages(), slots.take("account-a"))
        gc.collect()

        slots.take("account-a")


class TestStreamSlotsAtTheRoutes:
    def events(self, table_id):
        return f"{TABLES_PATH}/{table_id}{TABLE_EVENTS_SUFFIX}"

    def test_streams_of_both_kinds_count_against_one_limit_of_the_account_and_a_stranger_is_not_counted(
        self, sign_in_settings
    ):
        skat = Skat(lambda: sign_in_settings(streams_per_account=2))
        headers, _ = skat.member()
        table_id = skat.create(headers).json()["id"]
        stranger, _ = skat.member()
        skat.client.cookies.clear()

        def status_of(path, who):
            with skat.client.stream("GET", path, headers=who) as answer:
                return answer.status_code

        with (
            skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=headers),
            skat.client.stream("GET", self.events(table_id), headers=headers),
        ):
            over = [status_of(LOBBY_EVENTS_PATH, headers), status_of(self.events(table_id), headers)]
            stranger_gets = status_of(LOBBY_EVENTS_PATH, stranger)

        assert (over, stranger_gets) == ([429, 429], 200)

    def test_a_table_that_is_not_found_takes_no_slot(self, sign_in_settings):
        skat = Skat(lambda: sign_in_settings(streams_per_account=1))
        headers, _ = skat.member()
        skat.client.cookies.clear()

        unknown = [skat.client.get(self.events(UNKNOWN_ID), headers=headers).status_code for _ in range(2)]
        with skat.client.stream("GET", LOBBY_EVENTS_PATH, headers=headers) as answer:
            status = answer.status_code

        assert (unknown, status) == ([404, 404], 200)
