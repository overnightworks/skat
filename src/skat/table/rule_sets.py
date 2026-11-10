import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Protocol

from skat.table.records import RuleSetId, TableOptions

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager

    from skat.table.records import Actor

__all__ = [
    "RULE_SET_NAME_MAX",
    "DuplicateRuleSetError",
    "RuleSet",
    "RuleSetRefusal",
    "RuleSetService",
    "RuleSetTransaction",
    "RuleSetTransactions",
    "decide_save",
    "ordered",
    "rule_set_name",
]

RULE_SET_NAME_MAX: Final = 40


class RuleSetRefusal(StrEnum):
    NAME_TAKEN = "name-taken"


@dataclass(frozen=True)
class RuleSet:
    """The table options a person saved under a name; only its owner reads it."""

    id: RuleSetId
    owner_account: str
    name: str
    options: TableOptions


def rule_set_name(text: str) -> str | None:
    """The name a set is saved under: stripped, in Unicode NFC, 1 to 40 characters with no control character; None
    when the text is no name.
    """
    name = unicodedata.normalize("NFC", text.strip())
    if not 1 <= len(name) <= RULE_SET_NAME_MAX or any(unicodedata.category(each) == "Cc" for each in name):
        return None
    return name


def decide_save(owned: Iterable[RuleSet], candidate: RuleSet) -> RuleSet | RuleSetRefusal:
    """The owner's set of that name when it holds the same options, a refusal when it holds others, else the candidate
    itself.
    """
    held = next((each for each in owned if each.name == candidate.name), None)
    if held is None:
        return candidate
    return held if held.options == candidate.options else RuleSetRefusal.NAME_TAKEN


def ordered(sets: Iterable[RuleSet]) -> tuple[RuleSet, ...]:
    """The sets by case-folded name, then id."""
    return tuple(sorted(sets, key=lambda each: (each.name.casefold(), each.id.value)))


class DuplicateRuleSetError(Exception):
    """Another transaction stored a set of the same owner and name first."""


class RuleSetTransaction(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def sets_of(self, owner_account: str) -> tuple[RuleSet, ...]: ...

    def add(self, rule_set: RuleSet) -> None:
        """Store a new set; a set of the same owner and name raises `DuplicateRuleSetError`."""
        ...

    def delete(self, owner_account: str, rule_set_id: RuleSetId) -> bool:
        """Delete the owner's set; false when the owner holds none of this id."""
        ...


class RuleSetTransactions(Protocol):  # pragma: no cover - a port's method bodies are signatures; the adapters run
    def begin(self) -> AbstractContextManager[RuleSetTransaction]:
        """One transaction: it commits when the block ends and rolls back when the block raises."""
        ...


class RuleSetService:
    """Saves, lists and deletes the rule sets of the account that acts; each call is one transaction."""

    def __init__(
        self, transactions: RuleSetTransactions, *, new_rule_set_id: Callable[[], RuleSetId] = RuleSetId.random
    ) -> None:
        self._transactions = transactions
        self._new_rule_set_id = new_rule_set_id

    def sets(self, actor: Actor) -> tuple[RuleSet, ...]:
        with self._transactions.begin() as transaction:
            return ordered(transaction.sets_of(actor.account_id))

    def save(self, actor: Actor, name: str, options: TableOptions) -> RuleSet | RuleSetRefusal:
        try:
            return self._save_once(actor, name, options)
        except DuplicateRuleSetError:
            # A set of this name committed between this call's read and its write; the retry reads it.
            return self._save_once(actor, name, options)

    def _save_once(self, actor: Actor, name: str, options: TableOptions) -> RuleSet | RuleSetRefusal:
        with self._transactions.begin() as transaction:
            owned = transaction.sets_of(actor.account_id)
            decision = decide_save(owned, RuleSet(self._new_rule_set_id(), actor.account_id, name, options))
            if isinstance(decision, RuleSet) and decision not in owned:
                transaction.add(decision)
            return decision

    def delete(self, actor: Actor, rule_set_id: str) -> bool:
        parsed = RuleSetId.parse(rule_set_id)
        if parsed is None:
            return False
        with self._transactions.begin() as transaction:
            return transaction.delete(actor.account_id, parsed)
