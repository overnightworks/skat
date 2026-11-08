from skat.web.presence import ChairHold, Presence


class IdleScheduler:
    """A scheduler that never runs anything, for tests that do not look at the chair hold."""

    def schedule(self, delay, action):
        pass

    def cancel_all(self):
        pass


async def free_no_chair(table_id, account_id, still_due):
    return False


def idle_hold() -> ChairHold:
    return ChairHold(300, lambda: 0.0, IdleScheduler(), free_no_chair)


def idle_presence() -> Presence:
    return Presence(idle_hold())
