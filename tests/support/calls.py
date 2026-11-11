"""The facts of a person's call to an agent, with every fact in the call's favour unless a test changes one."""

from dataclasses import replace

from skat.table.member_place import CallFacts


def call_facts(agent_account: str, owner_account: str, inviter_account: str | None = None, **changes) -> CallFacts:
    """A call the table offers: the inviter, by default the owner, is present and a member, the agent listens and its
    owner is present. A change replaces the fact of its name.
    """
    facts = CallFacts(
        viewer_account=inviter_account or owner_account,
        viewer_present=True,
        viewer_is_member=True,
        agent_account=agent_account,
        agent_listens=True,
        owner_account=owner_account,
        owner_present=True,
    )
    return replace(facts, **changes)
