"""The record of an agent's name and owner in the Redis every pod shares: one key per account, which expires."""

from typing import TYPE_CHECKING

from agents.member import LEASE_SECONDS
from pydantic import BaseModel, ValidationError
from webauth.ports import AgentFacts

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from redis.asyncio import Redis as AsyncRedis


class _StoredFacts(BaseModel):
    name: str
    owner: str


def _facts_of(stored: bytes | str) -> AgentFacts | None:
    try:
        read = _StoredFacts.model_validate_json(stored)
    except ValidationError:
        return None
    return AgentFacts(owner=read.owner, name=read.name)


class RedisAgentRecords:
    """Each record lasts `LEASE_SECONDS` from its latest write, so an agent that stops calling is forgotten a lease
    after its last call; the writer that comes last wins.
    """

    def __init__(self, client: AsyncRedis, *, key_prefix: str) -> None:
        self._client = client
        self._key_prefix = key_prefix

    async def write(self, account_id: str, facts: AgentFacts) -> None:
        stored = _StoredFacts(name=facts.name, owner=facts.owner)
        await self._client.set(self._key(account_id), stored.model_dump_json(), ex=LEASE_SECONDS)

    async def read(self, account_ids: Collection[str]) -> Mapping[str, AgentFacts]:
        if not account_ids:
            return {}
        accounts = list(account_ids)
        stored = await self._client.mget([self._key(account_id) for account_id in accounts])
        read = {account: _facts_of(each) for account, each in zip(accounts, stored, strict=True) if each is not None}
        return {account: facts for account, facts in read.items() if facts is not None}

    def _key(self, account_id: str) -> str:
        return f"{self._key_prefix}:{account_id}"
