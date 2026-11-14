"""Whether a session's person may call agents is read once for the display and held, never per render; a call reads the
issuer fresh and replaces what is held; an answer is dropped once the session cap has passed.
"""

import asyncio

import pytest
from starlette.requests import Request
from webauth.oidc_login import AccessTokenRefusal, AccessTokenRefusalReason

from skat.web.calling import AGENT_ADDERS_GROUP, DISPLAY_REFUSAL_HOLD, CallerMembership
from tests.support.signed_in import cookie_header, new_account, seed_member
from tests.web.support.calling import call, listening, only_row, person, read_control
from tests.web.support.changes import RecordedChanges
from tests.web.support.skat import Skat, streams_of

NOVA = "agent-nova"


def refresh_requests(issuer):
    """Every refresh grant the issuer was asked for, the refused ones too."""
    return len([request for request, _ in issuer.exchanges if request.form["grant_type"] == "refresh_token"])


@pytest.fixture
def changes():
    return RecordedChanges()


@pytest.fixture
def skat(hold, issuer, time, changes):
    issuer.reuses_refresh_tokens = True
    skat = Skat(
        lambda: hold,
        issuer_transports=issuer.transports,
        chair_clock=time.clock,
        chair_scheduler=time,
        now=time.moment,
        resource_changes=changes.wired,
    )
    with skat.client:
        yield skat


@pytest.fixture
def felix(skat, issuer):
    return person(skat, issuer)


@pytest.fixture
def table_id(skat, felix):
    created = skat.create(felix.headers)
    skat.client.cookies.clear()
    return created.json()["id"]


@pytest.fixture
def watching(skat, felix, table_id):
    with streams_of(skat, table_id, [(felix.headers, None)]):
        yield


@pytest.mark.usefixtures("watching")
class TestTheDisplayReadsTheGroupsOncePerSession:
    def test_the_first_control_read_of_a_session_reads_them_and_every_further_one_none(
        self, skat, issuer, felix, table_id
    ):
        reads = [read_control(skat, felix, table_id).json()["shown"] for _ in range(3)]

        assert (reads, refresh_requests(issuer)) == ([True] * 3, 1)

    def test_every_session_of_a_person_has_its_own_answer(self, skat, issuer, felix, table_id):
        second_device = person(skat, issuer)
        with streams_of(skat, table_id, [(second_device.headers, None)]):
            read_control(skat, felix, table_id)
            read_control(skat, second_device, table_id)

        assert refresh_requests(issuer) == 2

    def test_a_refused_first_read_shows_no_control_and_is_held_for_five_minutes_then_read_again(
        self, skat, issuer, time, felix, table_id
    ):
        issuer.refuses_refresh_grants = True
        refused = read_control(skat, felix, table_id).json()["shown"]
        issuer.refuses_refresh_grants = False
        time.now += DISPLAY_REFUSAL_HOLD.total_seconds() - 1
        held = read_control(skat, felix, table_id).json()["shown"]
        requests_while_held = refresh_requests(issuer)
        time.now += 1
        read_again = read_control(skat, felix, table_id).json()["shown"]

        assert (refused, held, requests_while_held) == (False, False, 1)
        assert (read_again, refresh_requests(issuer)) == (True, 2)

    def test_a_call_reads_afresh_and_its_answer_replaces_the_held_one(self, skat, issuer, felix, table_id):
        with listening(skat, issuer, felix, "Nova", NOVA):
            key = only_row(skat, felix, table_id)["key"]
            issuer.grant_groups(felix.id, ())

            call(skat, felix, table_id, key)
            shown = read_control(skat, felix, table_id).json()["shown"]

        assert (shown, refresh_requests(issuer)) == (False, 2)

    def test_a_restarted_app_holds_no_answer_and_lists_an_agent_after_its_next_listen(
        self, skat, issuer, hold, felix, table_id
    ):
        with listening(skat, issuer, felix, "Nova", NOVA):
            only_row(skat, felix, table_id)
        restarted = Skat(
            lambda: hold,
            store=skat.store,
            stores=skat.stores,
            issuer_transports=issuer.transports,
            resource_changes=RecordedChanges().wired,
        )

        with restarted.client, streams_of(restarted, table_id, [(felix.headers, None)]):
            before = read_control(restarted, felix, table_id).json()
            with listening(restarted, issuer, felix, "Nova", NOVA):
                after = read_control(restarted, felix, table_id).json()

        assert (before, [row["name"] for row in after["rows"]]) == ({"shown": True, "rows": []}, ["Nova"])
        assert refresh_requests(issuer) == 2


class FakeGroups:
    """The issuer's answer to a read of one session's groups, and how many reads were asked."""

    def __init__(self, answer):
        self.answer = answer
        self.reads = 0

    async def of_session(self, session_id):
        self.reads += 1
        return self.answer


def request_of(skat):
    """A request carrying the cookie of a new session, and that session's id."""
    member = seed_member(skat.stores, skat.config, account=new_account(skat.stores, skat.config))
    request = Request({"type": "http", "headers": [(b"cookie", cookie_header(member.set_cookie_headers).encode())]})
    return request, member.session.id


def displayed(held, *requests):
    async def read():
        return [await held.displayed(request) for request in requests]

    return asyncio.run(read())


class TestAnAnswerHeldForTheSessionCap:
    @pytest.fixture
    def groups(self):
        return FakeGroups(frozenset({AGENT_ADDERS_GROUP}))

    @pytest.fixture
    def now(self):
        return [0.0]

    @pytest.fixture
    def cap(self, skat):
        return skat.config.session_lifetime.absolute_max_age_seconds

    @pytest.fixture
    def membership(self, skat, groups, now):
        return CallerMembership(groups, skat.config, "an-issuer", lambda: now[0])

    def test_is_dropped_at_the_next_control_read_of_anyone_once_the_cap_has_passed(
        self, skat, membership, groups, now, cap
    ):
        ended, _ = request_of(skat)
        other, _ = request_of(skat)
        displayed(membership, ended)
        now[0] = cap - 1
        displayed(membership, other)
        now[0] = cap

        displayed(membership, ended, other)

        assert groups.reads == 3

    def test_is_kept_while_the_cap_has_not_passed(self, skat, membership, groups, now, cap):
        standing, _ = request_of(skat)
        other, _ = request_of(skat)
        displayed(membership, standing, other)
        now[0] = cap - 1

        displayed(membership, standing, other)

        assert groups.reads == 2

    def test_is_held_from_the_read_that_made_it_not_from_the_start(self, skat, membership, groups, now, cap):
        late, _ = request_of(skat)
        now[0] = 1000
        displayed(membership, late)
        now[0] = 1000 + cap - 1

        displayed(membership, late)

        assert groups.reads == 1


class TestARefusedRead:
    @pytest.mark.parametrize("reason", list(AccessTokenRefusalReason))
    def test_answers_no_member_at_the_display_and_is_handed_on_by_a_call_whatever_the_reason(self, skat, reason):
        groups = FakeGroups(AccessTokenRefusal(reason))
        held = CallerMembership(groups, skat.config, "an-issuer", lambda: 0.0)
        request, _ = request_of(skat)

        assert displayed(held, request) == [False]
        assert asyncio.run(held.fresh(request)) == AccessTokenRefusal(reason)
