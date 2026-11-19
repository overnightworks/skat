"""What the pods share about the agents that call Skat: the port to the record of an agent's name and owner."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from webauth.ports import AgentFacts


class AgentRecords(Protocol):  # pragma: no cover - a port's method bodies are signatures; `RedisAgentRecords` runs
    """One short-lived record per agent account, which every pod writes and reads: what the agent's signed token said
    of its name and its owner. A call that fails raises, whatever the store raises.
    """

    async def write(self, account_id: str, facts: AgentFacts) -> None:
        """Keeps the facts for the account from now on, in place of any earlier record."""
        ...

    async def read(self, account_ids: Collection[str]) -> Mapping[str, AgentFacts]:
        """The record of each account that has a readable one; an account without one is left out."""
        ...

    async def delete(self, account_id: str) -> None:
        """Drops the account's record, so the agent is not listed until a write succeeds."""
        ...
