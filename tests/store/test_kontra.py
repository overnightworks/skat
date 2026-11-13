import pytest
from sqlalchemy import text

from skat.engine.deal import Position
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer, Word, WordSaid
from skat.store.migrate import create_store_engine
from skat.store.tables import PostgresTableTransactions
from skat.table.kontra import KontraCommand
from skat.table.playing import GiveUpCommand
from skat.table.records import Actor, CreateTable, NoWordSaid, OccupantKind, SendAway, SitDown, TableOptions
from skat.table.service import TableService
from tests.support.stored_game import Game, count_rows, nobody_connected, person, seated_game

pytestmark = pytest.mark.postgres

FOREHAND, MIDDLEHAND, REARHAND = Position.FOREHAND, Position.MIDDLEHAND, Position.REARHAND
KONTRA, RE, SUPRA, HIRSCH = Word.KONTRA, Word.RE, Word.SUPRA, Word.HIRSCH
UP_TO_HIRSCH = KontraOptions(KontraSayer.ANY_OPPONENT, KontraReach.UP_TO_HIRSCH, KontraDeadline.OWN_CARD)


@pytest.fixture
def game(service, transactions, stored):
    return seated_game(service, transactions, stored, TableOptions(kontra=UP_TO_HIRSCH))


def say(game, position, word, *, command_id, version=None, service=None):
    command = KontraCommand(command_id, game.table_id, game.record.version if version is None else version, word)
    return (service or game.service).say_kontra(game.actors[position], command, nobody_connected())


def all_four_words(game):
    """Kontra before any card, Re after forehand's lead, Supra and Hirsch after the first trick."""
    assert say(game, FOREHAND, KONTRA, command_id="kontra").refusal is None
    game.play_legally(1)
    assert say(game, MIDDLEHAND, RE, command_id="re").refusal is None
    game.play_legally(2, start=2)
    assert say(game, FOREHAND, SUPRA, command_id="supra").refusal is None
    assert say(game, MIDDLEHAND, HIRSCH, command_id="hirsch").refusal is None


def test_a_table_reads_back_the_kontra_options_it_was_opened_with(game):
    assert game.record.options.kontra == UP_TO_HIRSCH


def test_a_table_opened_without_kontra_reads_back_none(service, transactions, stored):
    table_id = service.create(person("Anna"), CreateTable(command_id="plain")).id

    assert stored(transactions, table_id).options.kontra is None


def test_the_words_read_back_in_order_each_with_the_cards_played_before_it(game):
    all_four_words(game)

    assert game.record.progress.words == (
        WordSaid(FOREHAND, KONTRA, 0),
        WordSaid(MIDDLEHAND, RE, 1),
        WordSaid(FOREHAND, SUPRA, 3),
        WordSaid(MIDDLEHAND, HIRSCH, 3),
    )


def test_a_restart_replays_the_words_of_the_hand_and_each_viewer_sees_the_same_doubling(game, database_url):
    all_four_words(game)
    before = {
        name: game.service.view(game.actors[position], game.table_id, nobody_connected())
        for name, position in (("forehand", FOREHAND), ("middlehand", MIDDLEHAND))
    }
    restarted_engine = create_store_engine(database_url)
    try:
        restarted = TableService(PostgresTableTransactions(restarted_engine))
        after = {
            name: restarted.view(game.actors[position], game.table_id, nobody_connected())
            for name, position in (("forehand", FOREHAND), ("middlehand", MIDDLEHAND))
        }
    finally:
        restarted_engine.dispose()

    assert after == before
    assert after["forehand"].hand.playing.kontra.factor == 16
    assert [each.word for each in after["forehand"].hand.playing.kontra.said] == [KONTRA, RE, SUPRA, HIRSCH]


def test_a_retry_stores_no_second_word(game, engine):
    version = game.record.version
    first = say(game, FOREHAND, KONTRA, command_id="kontra", version=version)

    again = say(game, FOREHAND, KONTRA, command_id="kontra", version=version)

    assert again == first
    assert count_rows(engine, "kontra_words") == 1


def test_a_refused_word_stores_nothing(game, engine):
    refused = say(game, MIDDLEHAND, KONTRA, command_id="declarer-kontra")

    assert refused.refusal is not None
    assert count_rows(engine, "kontra_words") == 0


def test_the_words_go_with_the_hand_and_the_entry_keeps_the_last_word_and_the_doubled_score(game, engine):
    all_four_words(game)
    command = GiveUpCommand(command_id="give-up", table_id=game.table_id, version=game.record.version)

    result = game.service.give_up(game.actors[MIDDLEHAND], command, nobody_connected())

    assert result.refusal is None
    assert count_rows(engine, "kontra_words") == 0
    (entry,) = game.record.game_list
    assert entry.kontra_word is HIRSCH
    with engine.connect() as connection:
        stored_word = connection.execute(text("SELECT kontra_word FROM game_list")).scalar_one()
    assert stored_word == "hirsch"


def answer_no_word(game, position, *, command_id, version=None, service=None):
    return say(game, position, None, command_id=command_id, version=version, service=service)


def test_an_answer_of_no_word_reads_back(game, engine):
    assert answer_no_word(game, FOREHAND, command_id="no-word").refusal is None

    assert game.record.progress.no_words == frozenset({NoWordSaid(FOREHAND, KONTRA)})
    assert count_rows(engine, "kontra_no_words") == 1


def test_a_restart_reads_the_answer_back_and_the_seat_is_not_awaited_again(game, database_url):
    answer_no_word(game, FOREHAND, command_id="no-word")
    before = game.service.view(game.actors[FOREHAND], game.table_id, nobody_connected())
    restarted_engine = create_store_engine(database_url)
    try:
        restarted = TableService(PostgresTableTransactions(restarted_engine))
        after = restarted.view(game.actors[FOREHAND], game.table_id, nobody_connected())
    finally:
        restarted_engine.dispose()

    assert after == before
    assert after.hand.playing.kontra.my_word_answered is True


def test_a_retry_and_a_second_answer_store_one_row_and_raise_the_version_once(game, engine):
    version = game.record.version
    first = answer_no_word(game, FOREHAND, command_id="no-word", version=version)

    retried = answer_no_word(game, FOREHAND, command_id="no-word", version=version)
    repeated = answer_no_word(game, FOREHAND, command_id="no-word-again")

    assert retried == first
    assert repeated.refusal is None
    assert game.record.version == version + 1
    assert count_rows(engine, "kontra_no_words") == 1


def test_a_refused_answer_stores_nothing(game, engine):
    refused = answer_no_word(game, MIDDLEHAND, command_id="declarer-no-word")

    assert refused.refusal is not None
    assert count_rows(engine, "kontra_no_words") == 0


def test_the_answers_go_with_the_hand(game, engine):
    answer_no_word(game, FOREHAND, command_id="no-word")
    command = GiveUpCommand(command_id="give-up", table_id=game.table_id, version=game.record.version)

    game.service.give_up(game.actors[MIDDLEHAND], command, nobody_connected())

    assert count_rows(engine, "kontra_no_words") == 0


def test_a_chair_that_changes_hands_takes_its_answer_out_of_the_store(service, transactions, stored, engine):
    agent = Actor(account_id=person("Ben").account_id, display_name="Ben", kind=OccupantKind.AGENT)
    table_id = service.create(
        person("Anna"), CreateTable(command_id="command-open", options=TableOptions(kontra=UP_TO_HIRSCH))
    ).id
    service.sit(agent, SitDown("command-ben", table_id, 2), nobody_connected())
    service.sit(person("Cleo"), SitDown("command-cleo", table_id, 3), nobody_connected())
    game = Game(service, transactions, stored, table_id)
    answer_no_word(game, FOREHAND, command_id="forehand-no-word")
    answer_no_word(game, REARHAND, command_id="rearhand-no-word")

    sender = game.actors[REARHAND]
    sent = service.send_away(
        sender,
        SendAway("send-away", table_id, game.actors[FOREHAND].account_id),
        frozenset({sender.account_id}),
        is_member=True,
    )

    assert sent.refusal is None
    assert game.record.progress.no_words == frozenset({NoWordSaid(REARHAND, KONTRA)})
    assert count_rows(engine, "kontra_no_words") == 1
