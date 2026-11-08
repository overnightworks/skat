"""Write the browser's typed copy of the paths and answer tokens the Python app owns.

The Python constants own the paths and the enums own the tokens; this generator renders them as TypeScript constants.
`--check` writes nothing and fails when the committed file differs from the rendering or is
missing, so CI catches drift.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "src"))

from skat.web.constants import (  # noqa: E402
    ACCOUNT_CONSOLE_PATH,
    ACCOUNT_PATH,
    AUTH_START_PATH,
    LOGOUT_PATH,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
)
from skat.web.tables import (  # noqa: E402
    TABLE_EVENTS_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
    PositionToken,
    RankToken,
    SuitToken,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from enum import StrEnum

OUTPUT = Path("frontend/src/lib/wire.ts")
CHECK_FLAG = "--check"
HEADER = "// Generated from the Python path and token owners by scripts/generate_wire.py. Do not edit.\n"
TOKEN_TUPLES: dict[str, type[StrEnum]] = {
    "SUIT_TOKENS": SuitToken,
    "RANK_TOKENS": RankToken,
    "POSITION_TOKENS": PositionToken,
}


def token_tuple(name: str, tokens: type[StrEnum]) -> str:
    listed = ", ".join(f'"{token.value}"' for token in tokens)
    return f"export const {name} = [{listed}] as const;\n"


def render() -> str:
    constants = {
        "AUTH_START_PATH": AUTH_START_PATH,
        "RETURN_PATH_QUERY_NAME": RETURN_PATH_QUERY_NAME,
        "SIGNED_IN_AGAIN_QUERY_NAME": SIGNED_IN_AGAIN_QUERY_NAME,
        "LOGOUT_PATH": LOGOUT_PATH,
        "ACCOUNT_PATH": ACCOUNT_PATH,
        "ACCOUNT_CONSOLE_PATH": ACCOUNT_CONSOLE_PATH,
        "TABLES_PATH": TABLES_PATH,
        "TABLE_PAGE_PREFIX": TABLE_PAGE_PREFIX,
        "TABLE_EVENTS_SUFFIX": TABLE_EVENTS_SUFFIX,
        "TABLE_SIT_SUFFIX": TABLE_SIT_SUFFIX,
        "TABLE_STAND_SUFFIX": TABLE_STAND_SUFFIX,
    }
    paths = "".join(f'export const {name} = "{path}";\n' for name, path in constants.items())
    tuples = "".join(token_tuple(name, tokens) for name, tokens in TOKEN_TUPLES.items())
    return HEADER + "\n" + paths + tuples


def main(arguments: Sequence[str], root: Path = REPOSITORY) -> int:
    target = root / OUTPUT
    rendered = render()
    if CHECK_FLAG in arguments:
        if not target.is_file() or target.read_text() != rendered:
            raise SystemExit(f"generate_wire: {target} out of date; run scripts/generate_wire.py without --check")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
