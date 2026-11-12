from sqlalchemy import text

from skat.engine.bock import BockOptions, BockOverlap, BockTrigger
from skat.engine.kontra import KontraDeadline, KontraOptions, KontraReach, KontraSayer
from skat.engine.ramsch import DurchmarschRule, JungfrauRule, RamschOptions, RamschScoring
from skat.store.rule_sets import PostgresRuleSets
from skat.table.records import RamschOccasion, RamschSetting, RuleSetId, TableOptions
from skat.table.rule_sets import RuleSet

# The columns a rule set has before the pushing revision; a later option column is none of their business.
INSERT_BEFORE_PUSHING = text(
    "INSERT INTO rule_sets (id, owner_account, name, show_running_points, kontra_sayer, kontra_reach,"
    " kontra_deadline, bock_triggers, bock_overlap, ramsch_occasion, ramsch_scoring, ramsch_jungfrau,"
    " ramsch_durchmarsch) VALUES (:id, :owner_account, :name, :show_running_points, :kontra_sayer, :kontra_reach,"
    " :kontra_deadline, CAST(:bock_triggers AS text[]), :bock_overlap, :ramsch_occasion, :ramsch_scoring,"
    " :ramsch_jungfrau, :ramsch_durchmarsch)"
)
SELECT_BEFORE_PUSHING = text(
    "SELECT id, owner_account, name, show_running_points, kontra_sayer, kontra_reach, kontra_deadline,"
    " bock_triggers, bock_overlap, ramsch_occasion, ramsch_scoring, ramsch_jungfrau, ramsch_durchmarsch"
    " FROM rule_sets WHERE owner_account = :account_id"
)


def sets_of(engine, account_id):
    with PostgresRuleSets(engine).begin() as transaction:
        return transaction.sets_of(account_id)


def save(engine, rule_set):
    with PostgresRuleSets(engine).begin() as transaction:
        transaction.add(rule_set)


def save_before_pushing(engine, rule_set):
    """Write a set into a database before the pushing revision, with the columns and values that revision has."""
    options = rule_set.options
    kontra = options.kontra
    bock = options.bock
    ramsch = options.ramsch
    values = {
        "id": rule_set.id.value,
        "owner_account": rule_set.owner_account,
        "name": rule_set.name,
        "show_running_points": options.show_running_points,
        "kontra_sayer": None if kontra is None else kontra.sayer.value,
        "kontra_reach": None if kontra is None else kontra.reach.value,
        "kontra_deadline": None if kontra is None else kontra.deadline.value,
        "bock_triggers": None if bock is None else sorted(trigger.value for trigger in bock.triggers),
        "bock_overlap": None if bock is None else bock.overlap.value,
        "ramsch_occasion": None if ramsch is None else ramsch.occasion.value,
        "ramsch_scoring": None if ramsch is None else ramsch.reckoning.scoring.value,
        "ramsch_jungfrau": None if ramsch is None else ramsch.reckoning.jungfrau.value,
        "ramsch_durchmarsch": None if ramsch is None else ramsch.reckoning.durchmarsch.value,
    }
    with engine.begin() as connection:
        connection.execute(INSERT_BEFORE_PUSHING, values)


def sets_before_pushing(engine, account_id):
    """The sets a database before the pushing revision holds, read with the columns it has; none plays pushing."""
    with engine.connect() as connection:
        rows = connection.execute(SELECT_BEFORE_PUSHING, {"account_id": account_id})
        return tuple(
            RuleSet(RuleSetId(row.id), row.owner_account, row.name, _options_before_pushing(row)) for row in rows
        )


def _options_before_pushing(row):
    kontra = None
    if row.kontra_sayer is not None:
        kontra = KontraOptions(
            KontraSayer(row.kontra_sayer), KontraReach(row.kontra_reach), KontraDeadline(row.kontra_deadline)
        )
    bock = None
    if row.bock_triggers is not None:
        bock = BockOptions(
            frozenset(BockTrigger(trigger) for trigger in row.bock_triggers), BockOverlap(row.bock_overlap)
        )
    ramsch = None
    if row.ramsch_occasion is not None:
        ramsch = RamschSetting(
            RamschOccasion(row.ramsch_occasion),
            RamschOptions(
                RamschScoring(row.ramsch_scoring),
                JungfrauRule(row.ramsch_jungfrau),
                DurchmarschRule(row.ramsch_durchmarsch),
            ),
        )
    return TableOptions(show_running_points=row.show_running_points, kontra=kontra, bock=bock, ramsch=ramsch)


OTHER_OPTIONS = TableOptions(show_running_points=True)


def a_set(owner, name, options=OTHER_OPTIONS):
    return RuleSet(RuleSetId.random(), owner, name, options)


def row_count(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM rule_sets")).scalar_one()
