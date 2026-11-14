import pytest

from skat.table.records import Refusal, TableStyle
from skat.table.style import StyleCommand, decide_style, style_payload
from tests.table.test_ready import ANNA, BEN, CLEO, DORA, TABLE_VERSION, pending


def styled(style: TableStyle, *, command_id: str = "command-style") -> StyleCommand:
    return StyleCommand(command_id=command_id, table_id="0" * 32, style=style)


class TestDecideStyle:
    def test_a_table_is_classic_until_a_member_changes_it(self):
        assert pending().style is TableStyle.KLASSIK

    @pytest.mark.parametrize("actor", [ANNA, BEN, CLEO], ids=["seat-1", "seat-2", "seat-3"])
    def test_a_seated_member_changes_the_style_and_bumps_the_version_once(self, actor):
        decision = decide_style(pending(), actor, styled(TableStyle.STRANDBAR))

        assert decision.refusal is None
        assert decision.table.style is TableStyle.STRANDBAR
        assert decision.table.version == TABLE_VERSION + 1

    def test_a_member_changes_it_back(self):
        beach = decide_style(pending(), ANNA, styled(TableStyle.STRANDBAR)).table

        decision = decide_style(beach, BEN, styled(TableStyle.KLASSIK))

        assert decision.table.style is TableStyle.KLASSIK

    def test_a_watcher_is_refused_and_the_table_stays_as_it_was(self):
        table = pending()

        decision = decide_style(table, DORA, styled(TableStyle.STRANDBAR))

        assert decision.refusal is Refusal.NOT_SEATED
        assert decision.table == table

    def test_the_style_a_table_already_has_is_accepted_with_no_new_version(self):
        table = pending()

        decision = decide_style(table, ANNA, styled(TableStyle.KLASSIK))

        assert decision.refusal is None
        assert decision.table == table

    def test_only_the_style_changes(self):
        table = pending(1)

        changed = decide_style(table, BEN, styled(TableStyle.STRANDBAR)).table

        assert (changed.chairs, changed.dealer, changed.game_list, changed.options, changed.visibility) == (
            table.chairs,
            table.dealer,
            table.game_list,
            table.options,
            table.visibility,
        )

    def test_the_receipt_payload_tells_one_style_from_another(self):
        assert style_payload(styled(TableStyle.KLASSIK)) != style_payload(styled(TableStyle.STRANDBAR))
