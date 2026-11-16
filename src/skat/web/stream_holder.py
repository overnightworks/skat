"""The name an open stream holds its presence lease under, and how a roster's names read back."""

import json
from dataclasses import dataclass
from typing import Self

from pydantic import TypeAdapter, ValidationError

_FIELDS = TypeAdapter(tuple[str, str, str])


class MalformedHolderError(ValueError):
    """A lease holder of the presence family that no stream of Skat wrote."""


@dataclass(frozen=True)
class StreamHolder:
    """One open stream: the table it watches, the account that watches and an id of the stream itself, so that an
    account in two tabs holds two leases.
    """

    table_id: str
    account_id: str
    stream_id: str

    def encoded(self) -> str:
        return json.dumps([self.table_id, self.account_id, self.stream_id], separators=(",", ":"))

    @classmethod
    def parse(cls, holder: str) -> Self:
        try:
            return cls(*_FIELDS.validate_json(holder, strict=True))
        except ValidationError as failure:
            raise MalformedHolderError from failure
