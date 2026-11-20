import threading

from sqlalchemy import select

from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.store.schema import series
from skat.table.ready import NewSeriesCommand
from skat.table.records import Actor, TableId, TableOptions

OPENER = Actor(account_id="account-opener", display_name="Anna")
VISITOR = Actor(account_id="account-visitor", display_name="Ben")
THIRD_PLAYER = Actor(account_id="account-third", display_name="Cleo")
PEOPLE = {1: OPENER, 2: VISITOR, 3: THIRD_PLAYER}
ALL_THREE = frozenset(person.account_id for person in PEOPLE.values())


def read(transactions, table_id):
    with transactions.begin() as transaction:
        return transaction.table(TableId(table_id))


def tap_all(service, table_id, round_name="new-series", series=1, settings=0):
    for seat, person in PEOPLE.items():
        command = NewSeriesCommand(f"{round_name}-{seat}", table_id, series, settings)
        assert service.start_new_series(person, command, ALL_THREE).refusal is None


def race(first, second):
    answers = {}

    def run(name, call):
        answers[name] = call()

    threads = [threading.Thread(target=run, args=item) for item in (("first", first), ("second", second))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return answers


def kontra_options(reach):
    return TableOptions(kontra=KontraOptions(KontraSayer.ANY_OPPONENT, reach, KontraDeadline.OWN_CARD))


FIRST_SERIES_OPTIONS = kontra_options(KontraReach.KONTRA_RE_STANDINGS)
SECOND_SERIES_OPTIONS = kontra_options(KontraReach.KONTRA_RE)


def series_rows(engine, table_id):
    with engine.connect() as connection:
        return connection.execute(select(series).where(series.c.table_id == table_id).order_by(series.c.number)).all()
