# skat

## Commands

`make -n <target>` prints a target; the targets are the `.PHONY` line of the `Makefile`.

- `make check`: lint, unit tests, dead-code scan and frontend checks; the local gate. Needs `make install` once and the Node and pnpm the frontend declares.
- `make lint`: ruff, pyright, import-linter and the generated-file checks.
- `make test`: the unit tests against a throwaway Postgres container, so Docker must run.
- `make e2e`: the end-to-end tests in Chromium; builds the page first, needs Playwright's Chromium installed once and Docker, and runs under the probe-stack `flock` of the global contract.
- `make run`: builds the page, then serves the app; the server refuses to start without that build.
- `make frontend-check`: svelte-check, the frontend linter and Vitest.
- `make wire`: regenerates `frontend/src/lib/wire.ts` from the Python path constants.
- `make words`: regenerates `frontend/src/lib/words.ts` from `frontend/src/lib/catalogs/de.po`.

## Rules

- Never edit `frontend/src/lib/wire.ts` or `frontend/src/lib/words.ts` by hand; change their source and regenerate.
- A setting added to or changed in `src/skat/web/settings.py` updates the Configuration table in `README.md` in the same change.
- A new Python package is placed in a layer of the import-linter contracts in `pyproject.toml`, which are exhaustive.
- A sonar marker takes the bare rule key, `# NOSONAR(S7503) reason`; a `language:`-prefixed key is a syntax finding itself. A ruff `# noqa: <code>` line's prose after the code has no comma, since SonarPython raised python:S7632 on one that did.

## Owners

- The operator decides the product, the game rules, the pictures, the legal texts and when a release starts (the `Release` workflow).
- overnightworks/quality owns the shared gate, `quality / verdict`; its README owns the gate's semantics, and `quality/config.toml` configures it here.

## Documents

- `README.md`: read when changing a setting, the release or how to run Skat.
- `docs/VISION.md`: read when judging what Skat should do or look like.
- `docs/ARCHITECTURE.md`: read when changing a part, a boundary, the trust model or a runtime flow; it holds the layer rule and its reasons.
- `docs/mockups/`: read when building a surface; the frozen pictures, one file per surface.
- `legal/`: read when the app processes new data; hal reads these two pages from each release at exactly these paths.
