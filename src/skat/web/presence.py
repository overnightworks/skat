from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, eq=False)
class Subscription:
    """One open stream. `wake` only signals that its view changed; the stream rebuilds the view itself."""

    table_id: str
    account_id: str
    wake: Callable[[], None]


class Presence:
    """Who is connected to which table, in this process only.

    Every call runs on the event loop's thread, so no lock guards the state. A wake carries no data: a stream
    that falls behind finds several changes folded into one wake and reads the latest state, which is its
    fresh snapshot.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._stopped = False

    @property
    def stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        """Wake every open stream to end; a stream that starts afterwards ends at once."""
        self._stopped = True
        self._wake_all([subscription for open_ones in self._subscriptions.values() for subscription in open_ones])

    def wake_table(self, table_id: str) -> None:
        """Tell every stream of a table that a committed write changed its view; call it after the commit."""
        self._wake_all(list(self._subscriptions.get(table_id, ())))

    def connected(self, table_id: str) -> frozenset[str]:
        return frozenset(subscription.account_id for subscription in self._subscriptions.get(table_id, ()))

    def subscribe(self, table_id: str, account_id: str, wake: Callable[[], None]) -> Subscription:
        """Register before the stream reads its view, so a change after this call wakes it."""
        subscription = Subscription(table_id, account_id, wake)
        already_connected = account_id in self.connected(table_id)
        others = list(self._subscriptions.get(table_id, ()))
        self._subscriptions.setdefault(table_id, []).append(subscription)
        if not already_connected:
            self._wake_all(others)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        remaining = self._subscriptions.get(subscription.table_id, [])
        if subscription not in remaining:
            return
        remaining.remove(subscription)
        if not remaining:
            del self._subscriptions[subscription.table_id]
        elif subscription.account_id not in self.connected(subscription.table_id):
            self._wake_all(remaining)

    @staticmethod
    def _wake_all(subscriptions: list[Subscription]) -> None:
        for subscription in subscriptions:
            subscription.wake()
