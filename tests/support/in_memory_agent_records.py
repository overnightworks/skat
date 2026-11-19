from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from webauth.ports import AgentFacts


class InMemoryAgentRecords:
    """The record of each agent's name and owner as every pod that shares this object sees it; a record lives until
    `forget`. `fails_writes` and `fails_reads` make the store answer nothing, as a Redis that is down does.
    """

    def __init__(self) -> None:
        self.records: dict[str, AgentFacts] = {}
        self.fails_writes = False
        self.fails_reads = False

    async def write(self, account_id: str, facts: AgentFacts) -> None:  # NOSONAR(S7503) the port is awaited
        if self.fails_writes:
            raise ConnectionError("redis is unreachable")
        self.records[account_id] = facts

    async def read(
        self, account_ids: Collection[str]
    ) -> Mapping[str, AgentFacts]:  # NOSONAR(S7503) the port is awaited
        if self.fails_reads:
            raise ConnectionError("redis is unreachable")
        return {account: self.records[account] for account in account_ids if account in self.records}

    def forget(self, account_id: str) -> None:
        """The record expired."""
        self.records.pop(account_id, None)
