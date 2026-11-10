import pytest

from skat.table.rule_sets import RULE_SET_NAME_MAX
from skat.web.constants import LOGOUT_PATH
from skat.web.rule_sets import RULE_SETS_PATH
from tests.support.sign_in_settings import TEST_PUBLIC_ORIGIN
from tests.web.support.skat import FETCH

EVENING = {"show_running_points": True}
FELIX = {"kontra": {"sayer": "bidders-only", "reach": "up-to-hirsch", "deadline": "own-card"}}
OFFICIAL = {"show_running_points": False, "kontra": None}
EVENING_ANSWER = {"show_running_points": True, "kontra": None}
FELIX_ANSWER = {"show_running_points": False, **FELIX}
SAME_ORIGIN = {"origin": TEST_PUBLIC_ORIGIN}


def save(skat, headers, name="Abend", options=EVENING, **extra):
    return skat.client.post(
        RULE_SETS_PATH, json={"name": name, "options": options, **extra}, headers={**SAME_ORIGIN, **headers}
    )


def read(skat, headers):
    return skat.client.get(RULE_SETS_PATH, headers=headers)


def delete(skat, headers, rule_set_id):
    return skat.client.delete(f"{RULE_SETS_PATH}/{rule_set_id}", headers={**SAME_ORIGIN, **headers})


def names_of(answer):
    return [each["name"] for each in answer.json()["sets"]]


class TestSaveAndRead:
    def test_a_saved_set_is_answered_and_listed_with_its_options(self, skat):
        headers, _ = skat.member()

        saved = save(skat, headers)
        listed = read(skat, headers)

        assert saved.status_code == 200
        assert saved.json() == {"id": saved.json()["id"], "name": "Abend", "options": EVENING_ANSWER}
        assert len(saved.json()["id"]) == 32
        assert listed.json() == {"sets": [saved.json()]}

    def test_a_set_with_no_options_holds_the_official_rules(self, skat):
        headers, _ = skat.member()

        assert save(skat, headers, options={}).json()["options"] == OFFICIAL

    def test_a_set_keeps_the_kontra_options_it_was_saved_with(self, skat):
        headers, _ = skat.member()

        save(skat, headers, "Felix", FELIX)

        assert read(skat, headers).json()["sets"][0]["options"] == FELIX_ANSWER

    def test_saving_a_name_again_with_the_same_options_answers_the_same_set(self, skat):
        headers, _ = skat.member()
        first = save(skat, headers)

        again = save(skat, headers)

        assert (again.status_code, again.json()) == (200, first.json())
        assert names_of(read(skat, headers)) == ["Abend"]

    def test_saving_a_name_with_other_options_is_refused_and_keeps_the_set(self, skat):
        headers, _ = skat.member()
        first = save(skat, headers)

        refused = save(skat, headers, options=FELIX)

        assert (refused.status_code, refused.json()) == (409, {"reason": "name-taken"})
        assert read(skat, headers).json() == {"sets": [first.json()]}

    def test_a_name_is_stripped_and_composed_before_it_is_kept_or_compared(self, skat):
        headers, _ = skat.member()
        padded = save(skat, headers, " Abend ")
        composed = save(skat, headers, "Café")

        decomposed = save(skat, headers, "Café")

        assert padded.json()["name"] == "Abend"
        assert decomposed.json() == composed.json()
        assert names_of(read(skat, headers)) == ["Abend", "Café"]

    def test_a_name_of_forty_characters_is_saved(self, skat):
        headers, _ = skat.member()

        assert save(skat, headers, "x" * RULE_SET_NAME_MAX).status_code == 200

    def test_sets_are_listed_by_case_folded_name(self, skat):
        headers, _ = skat.member()
        for name in ("skatabend", "Felix", "Abend"):
            save(skat, headers, name)

        assert names_of(read(skat, headers)) == ["Abend", "Felix", "skatabend"]

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"name": "", "options": {}}, id="empty-name"),
            pytest.param({"name": "   ", "options": {}}, id="blank-name"),
            pytest.param({"name": "x" * (RULE_SET_NAME_MAX + 1), "options": {}}, id="name-too-long"),
            pytest.param({"name": "Ab\x07end", "options": {}}, id="control-character"),
            pytest.param({"name": 7, "options": {}}, id="name-not-a-string"),
            pytest.param({"name": "Abend"}, id="no-options"),
            pytest.param({"name": "Abend", "options": {"bock": True}}, id="unknown-option"),
            pytest.param({"name": "Abend", "options": {"show_running_points": "yes"}}, id="option-of-the-wrong-type"),
            pytest.param({"name": "Abend", "options": {}, "owner": "account-ben"}, id="extra-key"),
        ],
    )
    def test_a_request_that_is_no_set_is_refused_and_stores_nothing(self, skat, body):
        headers, _ = skat.member()

        refused = skat.client.post(RULE_SETS_PATH, json=body, headers={**SAME_ORIGIN, **headers})

        assert refused.status_code == 422
        assert read(skat, headers).json() == {"sets": []}


class TestOwnership:
    def test_a_member_reads_only_their_own_sets(self, skat):
        anna, _ = skat.member()
        ben, _ = skat.member()
        save(skat, anna)

        assert read(skat, ben).json() == {"sets": []}

    def test_two_members_may_save_one_name_each_with_an_id_of_its_own(self, skat):
        anna, _ = skat.member()
        ben, _ = skat.member()
        annas = save(skat, anna)

        bens = save(skat, ben, options=FELIX)

        assert (bens.status_code, bens.json()["options"]) == (200, FELIX_ANSWER)
        assert bens.json()["id"] != annas.json()["id"]
        assert read(skat, anna).json() == {"sets": [annas.json()]}

    def test_another_member_deletes_nothing_and_learns_nothing(self, skat):
        anna, _ = skat.member()
        ben, _ = skat.member()
        saved = save(skat, anna)

        foreign = delete(skat, ben, saved.json()["id"])
        unknown = delete(skat, ben, "0" * 32)

        assert (foreign.status_code, foreign.json()) == (unknown.status_code, unknown.json())
        assert foreign.status_code == 404
        assert read(skat, anna).json() == {"sets": [saved.json()]}

    def test_the_sets_stay_when_the_member_signs_out_and_in_again(self, skat):
        first, account = skat.member()
        saved = save(skat, first)
        signed_out = skat.client.post(
            LOGOUT_PATH,
            headers={"origin": TEST_PUBLIC_ORIGIN, "content-type": "application/x-www-form-urlencoded", **first},
        )
        assert signed_out.status_code == 200

        second, _ = skat.member(account)

        assert read(skat, second).json() == {"sets": [saved.json()]}


class TestDelete:
    def test_the_owner_deletes_a_set_once(self, skat):
        headers, _ = skat.member()
        saved = save(skat, headers)

        first = delete(skat, headers, saved.json()["id"])
        second = delete(skat, headers, saved.json()["id"])

        assert (first.status_code, first.content) == (204, b"")
        assert second.status_code == 404
        assert read(skat, headers).json() == {"sets": []}

    @pytest.mark.parametrize("rule_set_id", ["not-an-id", "0" * 31, "A" * 32, "0" * 31 + "%00"])
    def test_a_malformed_id_deletes_nothing_and_is_not_found(self, skat, rule_set_id):
        headers, _ = skat.member()
        saved = save(skat, headers)

        refused = delete(skat, headers, rule_set_id)

        assert refused.status_code == 404
        assert read(skat, headers).json() == {"sets": [saved.json()]}


class TestOpeningATableWithASet:
    def test_the_table_answers_the_options_of_the_set_and_keeps_them_when_the_set_goes(self, skat):
        headers, _ = skat.member()
        saved = save(skat, headers, "Felix", FELIX)

        opened = skat.create(headers, options=saved.json()["options"])
        delete(skat, headers, saved.json()["id"])
        read_again = skat.client.get(f"/api/tables/{opened.json()['id']}", headers=headers)

        assert opened.json()["options"] == FELIX_ANSWER
        assert read_again.json()["options"] == FELIX_ANSWER
        assert "rule_set" not in opened.text


class TestNoStore:
    def test_every_answer_of_the_three_routes_forbids_a_cache(self, skat):
        headers, _ = skat.member()
        saved = save(skat, headers)
        answers = [
            saved,
            save(skat, headers, options=FELIX),
            read(skat, headers),
            delete(skat, headers, saved.json()["id"]),
            delete(skat, headers, saved.json()["id"]),
        ]

        assert [answer.headers["cache-control"] for answer in answers] == ["no-store"] * len(answers)


class TestRefusedRequests:
    def test_a_request_without_a_session_changes_and_reads_nothing(self, skat):
        headers, _ = skat.member()
        saved = save(skat, headers)
        skat.client.cookies.clear()

        answers = [
            skat.client.get(RULE_SETS_PATH, headers=FETCH),
            skat.client.post(RULE_SETS_PATH, json={"name": "Neu", "options": {}}, headers={**SAME_ORIGIN, **FETCH}),
            skat.client.delete(f"{RULE_SETS_PATH}/{saved.json()['id']}", headers={**SAME_ORIGIN, **FETCH}),
        ]

        assert [answer.status_code for answer in answers] == [401, 401, 401]
        assert read(skat, headers).json() == {"sets": [saved.json()]}

    def test_a_save_from_another_origin_stores_nothing(self, skat):
        headers, _ = skat.member()

        refused = skat.client.post(
            RULE_SETS_PATH,
            json={"name": "Abend", "options": {}},
            headers={"origin": "https://evil.example", **headers},
        )

        assert refused.status_code == 403
        assert read(skat, headers).json() == {"sets": []}
