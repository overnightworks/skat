"""Write the browser's typed copy of Skat's German texts.

The catalog owns every visible text; this generator renders it as one TypeScript object, so a text a
component uses but the catalog lacks fails the type check. A key without a translation fails the
generator and names the key. `--check` writes nothing and fails when the committed file differs from the
rendering or is missing, so CI catches drift.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING

from babel.messages.pofile import read_po

if TYPE_CHECKING:
    from collections.abc import Sequence

REPOSITORY = Path(__file__).resolve().parent.parent
CATALOG = Path("frontend/src/lib/catalogs/de.po")
OUTPUT = Path("frontend/src/lib/words.ts")
CHECK_FLAG = "--check"
HEADER = "// Generated from the German catalog by scripts/generate_words.py. Do not edit.\n"


def render(catalog_path: Path) -> str:
    with catalog_path.open("rb") as catalog_file:
        catalog = read_po(catalog_file, locale="de")
    texts = {str(message.id): str(message.string) for message in catalog if message.id}
    untranslated = [key for key, text in texts.items() if not text.strip()]
    if untranslated:
        raise SystemExit(f"generate_words: {catalog_path} has no translation for: {', '.join(untranslated)}")
    entries = "".join(f"    {key}: {json.dumps(text, ensure_ascii=False)},\n" for key, text in texts.items())
    return f"{HEADER}\nexport const words = {{\n{entries}}} as const;\n"


def main(arguments: Sequence[str], root: Path = REPOSITORY) -> int:
    target = root / OUTPUT
    rendered = render(root / CATALOG)
    if CHECK_FLAG in arguments:
        if not target.is_file() or target.read_text() != rendered:
            raise SystemExit(f"generate_words: {target} out of date; run scripts/generate_words.py without --check")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
