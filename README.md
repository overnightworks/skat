# Skat

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![CI](https://github.com/overnightworks/skat/actions/workflows/ci.yml/badge.svg)](https://github.com/overnightworks/skat/actions/workflows/ci.yml)

Skat is the classic German three-player card game for the overnightworks fleet: a table that people and their own agents play at, on its own or on a HopIn call's stage. Why it exists and what it is deliberately not: [docs/VISION.md](docs/VISION.md). How it is built and what it trusts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Today a signed-in member reaches Skat's start page and opens a table with „Neuer Tisch“: the member sits in chair 1 of a table with two free chairs and shares its link, `/t/{id}`, which shows the same table to every member. Sitting down and playing come next.

- A visitor without a session sees Skat's sign-in page, whose link leads to the issuer.
- A member of the Keycloak group `/apps/skat` sees the start page and can open any number of tables.
- A member who sits at tables sees each one under „Meine Tische“ on the start page, live, and opens one with a tap.
- Anyone else who signs in sees a refusal and no app content.
- Signing out ends the session and returns to the sign-in page.

## Quick start

You need Python 3.14+, [uv](https://docs.astral.sh/uv/), Node 24 or 26 and pnpm. `make install` installs the Python side, and `make run` builds the page (`make frontend`) and starts `skat serve`. The server refuses to start without the page build, without the settings below and against a database that is not at the newest migration; `skat migrate` brings it there and needs only `SKAT_DATABASE_URL` and `SKAT_DATABASE_PASSWORD_FILE` and reads `SKAT_OPERATOR_ACCOUNT_ID` when set.

Sign-in returns the person to `SKAT_PUBLIC_ORIGIN`, which must be https, so open Skat at that origin (behind a TLS-terminating proxy), not at the plain listen address. The issuer needs a client whose redirect URI is `SKAT_PUBLIC_ORIGIN` + `/auth/callback` and that sends the groups claim.

The tests that touch the database run against a throwaway Postgres: `make test` and `make e2e` start one through `scripts/test_postgres.sh`, which needs Docker. `make check` runs the lint, the unit tests, the dead-code check and the frontend checks; `make e2e` drives the browser tests and needs Playwright's Chromium installed once.

## Configuration

Every setting is an environment variable. The secrets are read from the files named, never from the environment.

| Variable | Default | Meaning |
|---|---|---|
| `SKAT_OIDC_ISSUER` | required | The realm's issuer URL, without a trailing slash. |
| `SKAT_OIDC_CLIENT_ID` | `skat` | The issuer's client for Skat. |
| `SKAT_OIDC_CLIENT_SECRET_FILE` | required | Absolute path of the file holding the client secret. |
| `SKAT_PUBLIC_ORIGIN` | required | The https origin people open Skat at, written as the browser writes an origin: a lowercase host, no path, no port 443. |
| `SKAT_CALL_ORIGIN` | unset | The one https origin whose pages may frame Skat, in the same form as `SKAT_PUBLIC_ORIGIN`. Unset or empty, no page may. |
| `SKAT_SESSION_SECRET_FILE` | required | Absolute path of the file holding the session signing key. |
| `SKAT_DATABASE_URL` | required | The Postgres connection URL without a password, as `postgresql://user@host/database`; Skat refuses to start if it carries a password or any query parameter. |
| `SKAT_DATABASE_PASSWORD_FILE` | required | Absolute path of the file holding only the database password. |
| `SKAT_OPERATOR_ACCOUNT_ID` | unset | The sign-in account id of the operator. `skat migrate` reads it when it runs and installs the operator's rule set „Felix“ on that account, or replaces it keeping its id; unset or empty, no set is installed. A migration applies once, so set it before the first `skat migrate` that reaches the revision. |
| `SKAT_TRUSTED_PROXIES` | empty | Addresses and CIDR blocks, comma-separated, of the proxies allowed to name the client in `X-Forwarded-For`. |
| `SKAT_CHAIR_HOLD_SECONDS` | `300` | How long a seated member whose last stream ended keeps the chair at a table on which no hand was dealt; a positive number. At a table on which a hand was dealt the chair is kept until its holder stands up or the table ends. |
| `SKAT_EMPTY_TABLE_SECONDS` | `1800` | How long a table on which no hand was dealt stays after nobody is connected to it, before it ends; a positive whole number. |
| `SKAT_PAUSED_TABLE_DAYS` | `90` | How many days after its last deal or step of play a table on which a hand was dealt ends, as each paused entry's `ends_at` names; a positive whole number, at most 36500. |
| `SKAT_HOST` | `0.0.0.0` | The listen address. |
| `SKAT_PORT` | `8080` | The listen port. |

## Release

A release is the `Release` workflow, which the operator dispatches with a version `YYYY.MM.DD.N`. It gates `main`, builds and attests the image `ghcr.io/overnightworks/skat` and tags `vYYYY.MM.DD.N`. CI builds the same image without pushing it.

## Licence

[MIT](LICENSE)
