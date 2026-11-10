from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from skat.table.rule_sets import RULE_SET_NAME_MAX, RuleSet, RuleSetRefusal, rule_set_name
from skat.web.mcp import READ_RULE_SETS_MARK, SAVE_RULE_SET_MARK, Exclusion, excluded
from skat.web.tables import OptionsAnswer, OptionsRequest, actor_of, options_answer_of, table_options_of

if TYPE_CHECKING:
    from skat.table.rule_sets import RuleSetService

RULE_SETS_PATH: Final = "/api/rule-sets"
# A name is its owner's text, so no cache may keep an answer past the gate.
NO_STORE: Final = {"Cache-Control": "no-store"}


class SaveRuleSetRequest(BaseModel):
    """A client names the set's name and options: its owner comes from the session."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(strict=True)]
    options: OptionsRequest

    @field_validator("name")
    @classmethod
    def _name_is_a_name(cls, text: str) -> str:
        name = rule_set_name(text)
        if name is None:
            message = f"a name has 1 to {RULE_SET_NAME_MAX} characters and no control character"
            raise ValueError(message)
        return name


class RuleSetAnswer(BaseModel):
    id: str
    name: str
    options: OptionsAnswer


class RuleSetsAnswer(BaseModel):
    sets: list[RuleSetAnswer]


class RuleSetRefusalAnswer(BaseModel):
    reason: RuleSetRefusal


def rule_set_answer_of(rule_set: RuleSet) -> RuleSetAnswer:
    return RuleSetAnswer(id=rule_set.id.value, name=rule_set.name, options=options_answer_of(rule_set.options))


def create_rule_sets_router(rule_sets: RuleSetService) -> APIRouter:
    router = APIRouter()

    @router.get(RULE_SETS_PATH, openapi_extra=READ_RULE_SETS_MARK)
    async def read_rule_sets(request: Request, response: Response) -> RuleSetsAnswer:
        """Read the caller's own saved rule sets, ordered by name: each with its id, its name and the table options it
        holds, in the same shape as a table's `options`. A rule set belongs to the account that saved it; nobody else
        reads it.
        """
        response.headers.update(NO_STORE)
        held = await run_in_threadpool(rule_sets.sets, actor_of(request))
        return RuleSetsAnswer(sets=[rule_set_answer_of(each) for each in held])

    @router.post(
        RULE_SETS_PATH,
        response_model=RuleSetAnswer,
        responses={409: {"model": RuleSetRefusalAnswer, "description": "The name holds other options."}},
        openapi_extra=SAVE_RULE_SET_MARK,
    )
    async def save_rule_set(body: SaveRuleSetRequest, request: Request, response: Response) -> Response | RuleSetAnswer:
        """Save the given table options under a name as one of the caller's own rule sets, and answer the set.
        `options` takes the same fields as a table's `options`; `{}` holds the official rules. Saving a name the
        caller already holds with the same options answers that set again and changes nothing; with other options it
        is refused with the reason `name-taken`, and nothing changes. A set is copied into a table when the table is
        opened with its options; changing the set later never changes such a table.
        """
        response.headers.update(NO_STORE)
        options = table_options_of(body.options)
        saved = await run_in_threadpool(rule_sets.save, actor_of(request), body.name, options)
        if isinstance(saved, RuleSetRefusal):
            refusal = RuleSetRefusalAnswer(reason=saved)
            return JSONResponse(refusal.model_dump(mode="json"), status_code=409, headers=NO_STORE)
        return rule_set_answer_of(saved)

    @router.delete(
        RULE_SETS_PATH + "/{rule_set_id}",
        status_code=204,
        responses={404: {"description": "The caller holds no rule set with this id."}},
        openapi_extra=excluded(Exclusion.FINAL_DELETION),
    )
    async def delete_rule_set(rule_set_id: str, request: Request) -> Response:
        deleted = await run_in_threadpool(rule_sets.delete, actor_of(request), rule_set_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="rule set not found", headers=NO_STORE)
        return Response(status_code=204, headers=NO_STORE)

    return router
