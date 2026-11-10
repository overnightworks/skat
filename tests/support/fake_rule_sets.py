import copy
from contextlib import contextmanager
from typing import TYPE_CHECKING

from skat.table.rule_sets import DuplicateRuleSetError, RuleSet

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skat.table.records import RuleSetId


class FakeRuleSetStore:
    """The rule-set port in memory: a block that raises leaves the store as it found it, and one owner never holds
    two sets of a name, as the database's unique key refuses.
    """

    def __init__(self) -> None:
        self.rule_sets: dict[str, RuleSet] = {}

    @contextmanager
    def begin(self) -> Iterator[FakeRuleSetStore]:
        before = copy.deepcopy(self.rule_sets)
        try:
            yield self
        except BaseException:
            self.rule_sets = before
            raise

    def sets_of(self, owner_account: str) -> tuple[RuleSet, ...]:
        return tuple(each for each in self.rule_sets.values() if each.owner_account == owner_account)

    def add(self, rule_set: RuleSet) -> None:
        if any(
            each.owner_account == rule_set.owner_account and each.name == rule_set.name
            for each in self.rule_sets.values()
        ):
            raise DuplicateRuleSetError
        self.rule_sets[rule_set.id.value] = rule_set

    def delete(self, owner_account: str, rule_set_id: RuleSetId) -> bool:
        held = self.rule_sets.get(rule_set_id.value)
        if held is None or held.owner_account != owner_account:
            return False
        del self.rule_sets[rule_set_id.value]
        return True
