# skat

## Commands

`make -n <target>` prints a target; the targets are the `.PHONY` line of the `Makefile`.

- `make lint`: ruff, pyright, import-linter and the generated-file checks; the static check to run locally. Needs `make install` once.
- `scripts/test_stores.sh uv run pytest <module or -k expression>`: the named unit tests against a throwaway Postgres and Redis, so Docker must run. The full suite (`make test`, `make check`) runs in CI, not locally.
- `scripts/test_stores.sh probe-run uv run pytest tests/e2e/<module>.py --no-cov --output test-results`: one end-to-end module in Chromium; run `make frontend` first, and install Playwright's Chromium once. The full run (`make e2e`) runs in CI, not locally.
- `cd frontend && pnpm check && pnpm lint`: svelte-check and the frontend linter, which stay local; needs the Node and pnpm the frontend declares. `pnpm exec vitest run <file>...` runs named Vitest files; `make frontend-check` and `pnpm test` over the whole tree run in CI, not locally.
- `make run`: builds the page, then serves the app; the server refuses to start without that build.
- `make wire`: regenerates `frontend/src/lib/wire.ts` from the Python path constants, token enums and table answer models.
- `make words-sync`: brings every further language's catalog in line with `de.po` by key; the model that writes a translation runs it before translating.
- `make words`: regenerates `frontend/src/lib/words/` and `src/skat/web/words.py` from the catalogs in `frontend/src/lib/catalogs/`.
- `make voice`: records the voice, one MP3 per `voice.` catalog key and language, through a local run of overnightworks/speech; the script's docstring names the settings it needs. It keeps recordings that exist; `--again` makes all anew. Needs `ffmpeg`.

## Rules

- Never edit `frontend/src/lib/wire.ts`, `frontend/src/lib/words/` or `src/skat/web/words.py` by hand; change their source and regenerate.
- A setting added to or changed in `src/skat/web/settings.py` updates the Configuration table in `README.md` in the same change.
- A new Python package is placed in a layer of the import-linter contracts in `pyproject.toml`, which are exhaustive.
- A sonar marker takes the bare rule key, `# NOSONAR(S7503) reason`; a `language:`-prefixed key is a syntax finding itself. A ruff `# noqa: <code>` line's prose after the code has no comma.

## Owners

- overnightworks/quality owns the shared gate, `quality / verdict`; its README owns the gate's semantics, and `quality/config.toml` configures it here.

## Documents

- `README.md`: read when changing a setting, the release or how to run Skat.
- `docs/VISION.md`: read when judging what Skat should do or look like.
- `docs/ARCHITECTURE.md`: read when changing a part, a boundary, the trust model or a runtime flow; it holds the layer rule and its reasons.
- `docs/mockups/`: read when building a surface; the frozen pictures, one file per surface.
- `legal/`: read when the app processes new data; hal reads these two pages from each release at exactly these paths.
