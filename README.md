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

You need Python 3.14+, [uv](https://docs.astral.sh/uv/), Node 24 or 26 and pnpm. `make install` installs the Python side, and `make run` builds the page (`make frontend`) and starts `skat serve`. The server refuses to start without the page build, without the settings below and against a database that does not list its revision as served; `skat migrate` brings the database there, keeps the release before it listed as served for a rollout, and needs only `SKAT_DATABASE_URL` and `SKAT_DATABASE_PASSWORD_FILE` and reads `SKAT_OPERATOR_ACCOUNT_ID` when set.

Sign-in returns the person to `SKAT_PUBLIC_ORIGIN`, which must be https, so open Skat at that origin (behind a TLS-terminating proxy), not at the plain listen address. The issuer needs a client whose redirect URI is `SKAT_PUBLIC_ORIGIN` + `/auth/callback` and that sends the groups claim.

The tests that touch the database or Redis run against a throwaway Postgres and Redis: `make test` and `make e2e` start one through `scripts/test_stores.sh`, together with a throwaway Redis, which needs Docker. `make check` runs the lint, the unit tests, the dead-code check and the frontend checks; `make e2e` drives the browser tests and needs Playwright's Chromium installed once.

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
| `SKAT_REDIS_URL` | required | The URL of the Redis every pod shares, as `redis://host:6379/0` (`rediss://` for TLS); Skat refuses to start if it carries credentials or any query parameter. Redis keeps the sign-in and request limits, which hold across pods, carries the wakes that tell every pod's streams a table changed, counts who watches which table through a lease per open stream that lapses 30 seconds after a pod dies, tells every pod which agents listen and what changed for them, and holds each agent's name and owner for a lease from its latest call; it holds nothing durable. A pod refuses to start without a subscription to the wakes within ten seconds. While it cannot answer, every request but `/health` is refused with a 503. `skat migrate` does not read it. |
| `SKAT_OPERATOR_ACCOUNT_ID` | unset | The sign-in account id of the operator. `skat migrate` reads it when it runs and installs the operator's rule set „Felix“ on that account, or replaces it keeping its id; unset or empty, no set is installed. A migration applies once, so set it before the first `skat migrate` that reaches the revision. |
| `SKAT_TRUSTED_PROXIES` | empty | Addresses and CIDR blocks, comma-separated, of the proxies allowed to name the client in `X-Forwarded-For`. |
| `SKAT_CHAIR_HOLD_SECONDS` | `300` | How long a seated member whose last stream ended keeps the chair at a table on which no hand was dealt; a positive number. At a table on which a hand was dealt the chair is kept until its holder stands up or the table ends. |
| `SKAT_EMPTY_TABLE_SECONDS` | `1800` | How long a table on which no hand was dealt stays after nobody is connected to it, before it ends; a positive whole number. |
| `SKAT_PAUSED_TABLE_DAYS` | `90` | How many days after its last deal or step of play a table on which a hand was dealt ends by itself, as each paused entry's `ends_at` names; Skat checks at its start and every hour, and a table that ends keeps every finished game in the history. A positive whole number, at most 36500. |
| `SKAT_ENDED_TABLE_DAYS` | `7` | How many days after its end an ended table's link names why it ended; Skat checks at its start and every hour, then deletes a table with no finished game together with its create receipt, so its link reads „Tisch nicht gefunden“, and clears the name of the opener who closed a table with games before „Aufhören“ replaced the close, whose link then reads „Tisch geschlossen“. A positive whole number, at most 36500. |
| `SKAT_STREAMS_PER_ACCOUNT` | `12` | How many lobby and table streams one account may hold open at once; one more gets a 429 before anything is held open, and closing a stream frees its slot. A positive whole number. |
| `SKAT_HOST` | `0.0.0.0` | The listen address. |
| `SKAT_PORT` | `8080` | The listen port. |
| `LOG_LEVEL` | `info` | The root logging threshold, read by [logline](https://github.com/overnightworks/logline): `debug`, `info`, `warning`, `error` or `critical`, in any letter case; Skat refuses to start on anything else. Request lines stay at `info` whatever it is set to. |
| `SERVICE_VERSION` | unset | The `version` of every log line. The image sets it to its release. |

## Release

A release is the `Release` workflow, which the operator dispatches with a version `YYYY.MM.DD.N`. It gates `main`, builds and attests the image `ghcr.io/overnightworks/skat` and tags `vYYYY.MM.DD.N`. CI builds the same image without pushing it.

## Licence

[MIT](LICENSE)
