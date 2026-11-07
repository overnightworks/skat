# Skat - Agent Guidance

This file holds Skat's own facts on top of the global contract. `CLAUDE.md`
imports it.

## Commands

The `Makefile` owns the targets. Traps:

- `make e2e` and `make run` build the page first (`make frontend`, which needs
  Node 26 or 24, and pnpm), and the server refuses to start without that build.
  `make e2e` takes no lock itself: run it under the `flock` rule in the global
  contract's section "Machine load and local runs". It needs Playwright's
  Chromium installed once; the `End-to-end` job in `.github/workflows/ci.yml`
  owns that install step.
- `make wire-check` (part of `make lint`) fails when `frontend/src/lib/wire.ts`
  drifts from the Python path constants; regenerate it with `make wire`.
- CI's `Coverage` job judges 100 % over unit and end-to-end data together, and
  the merged frontend report (Vitest and the browser) at 100 % lines, branches
  and functions; no local run judges it.
- pyright runs strict over `src` and `scripts`; `tests` are not type-checked.

## Where things live

- A setting added to or changed in `src/skat/web/settings.py` updates README's
  Configuration table in the same change.
- Layers are `skat.host` above `skat.web`; `pyproject.toml` holds the
  import-linter contracts, and a new package is placed in a layer there.
- `quality/config.toml` configures the shared gate and has no `legacy` key, so
  legacy findings only report; `quality/baseline.toml` holds the size ratchet's
  baseline. The required check is `quality / verdict`; overnightworks/quality's
  README owns the gate's semantics.
- `release.yml` calls quality's release workflows at a commit of quality's
  `main`, because no quality tag carries them yet; move the pin to the first
  tag that does.

## Scanner exceptions

- The scanner marker traps are in the `sonar-distributor` skill, section
  "Marker grammar".
