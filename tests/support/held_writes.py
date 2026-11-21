import threading
from contextlib import contextmanager

from tests.support.faulty_tables import HANG_DEADLINE_SECONDS
from tests.support.seated_tables import NOBODY_CONNECTED


class HeldWrite:
    """A write guard that waits in its worker until released, so the transaction that entered it keeps the row lock."""

    def __init__(self, connected=NOBODY_CONNECTED):
        self._connected = connected
        self.entered = threading.Event()
        self.release = threading.Event()

    def __enter__(self):
        self.entered.set()
        assert self.release.wait(HANG_DEADLINE_SECONDS)
        return self._connected

    def __exit__(self, *_):
        return None


class HoldingAfterSave:
    """A transactions port whose saves wait in their worker until `hold` is released, so the command that saved keeps
    the row lock it took.
    """

    def __init__(self, inner, hold):
        self._inner = inner
        self._hold = hold

    @contextmanager
    def begin(self):
        with self._inner.begin() as transaction:
            yield _HoldingTransaction(transaction, self._hold)


class _HoldingTransaction:
    def __init__(self, inner, hold):
        self._inner = inner
        self._hold = hold

    # the delegation of a wrapper to the store it wraps; each wrapper has its own methods
    def __getattr__(self, name):
        return getattr(self._inner, name)

    def save_table(self, table, *, played_at):
        self._inner.save_table(table, played_at=played_at)
        with self._hold:
            pass

    def end_table(self, table_id, ended_at, ending):
        self._inner.end_table(table_id, ended_at, ending)
        with self._hold:
            pass
