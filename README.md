# Skat

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![CI](https://github.com/overnightworks/skat/actions/workflows/ci.yml/badge.svg)](https://github.com/overnightworks/skat/actions/workflows/ci.yml)

Skat is the classic German three-player card game for the overnightworks fleet: a table that people and their own agents play at, on its own or on a HopIn call's stage. Why it exists and what it is deliberately not: [docs/VISION.md](docs/VISION.md). How it is built and what it trusts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Today a signed-in member reaches Skat's start page and opens a table with „Neuer Tisch“: the member sits in chair 1 of a table with two free chairs and shares its link, `/t/{id}`, which shows the same table to every member. Sitting down and playing come next.

- A visitor without a session sees Skat's sign-in page, whose link leads to the issuer.
- A member of the Keycloak group `/apps/skat` sees the start page and can open any number of tables.
- Anyone else who signs in sees a refusal and no app content.
- Signing out ends the session and returns to the sign-in page.

## Quick start

You need Python 3.14+, [uv](https://docs.astral.sh/uv/), Node 24 or 26 and pnpm. `make install` installs the Python side, and `make run` builds the page (`make frontend`) and starts `skat serve`. The server refuses to start without the page build, without the settings below and against a database that is not at the newest migration; `skat migrate` brings it there and needs only `SKAT_DATABASE_URL_FILE`.

Sign-in returns the person to `SKAT_PUBLIC_ORIGIN`, which must be https, so open Skat at that origin (behind a TLS-terminating proxy), not at the plain listen address. The issuer needs a client whose redirect URI is `SKAT_PUBLIC_ORIGIN` + `/auth/callback` and that sends the groups claim.

The tests that touch the database run against a throwaway Postgres: `make test` and `make e2e` start one through `scripts/test_postgres.sh`, which needs Docker. `make check` runs the lint, the unit tests, the dead-code check and the frontend checks; `make e2e` drives the browser tests and needs Playwright's Chromium installed once.

## Configuration

Every setting is an environment variable. The secrets and the database URL are read from the files named, never from the environment.

| Variable | Default | Meaning |
|---|---|---|
| `SKAT_OIDC_ISSUER` | required | The realm's issuer URL, without a trailing slash. |
| `SKAT_OIDC_CLIENT_ID` | `skat` | The issuer's client for Skat. |
| `SKAT_OIDC_CLIENT_SECRET_FILE` | required | Absolute path of the file holding the client secret. |
| `SKAT_PUBLIC_ORIGIN` | required | The https origin people open Skat at, without a path. |
| `SKAT_SESSION_SECRET_FILE` | required | Absolute path of the file holding the session signing key. |
| `SKAT_DATABASE_URL_FILE` | required | Absolute path of the file holding the Postgres connection URL, as `postgresql://user:password@host/database`. |
| `SKAT_TRUSTED_PROXIES` | empty | Addresses and CIDR blocks, comma-separated, of the proxies allowed to name the client in `X-Forwarded-For`. |
| `SKAT_HOST` | `0.0.0.0` | The listen address. |
| `SKAT_PORT` | `8080` | The listen port. |

## Release

A release is the `Release` workflow, which the operator dispatches with a version `YYYY.MM.DD.N`. It gates `main`, builds and attests the image `ghcr.io/overnightworks/skat` and tags `vYYYY.MM.DD.N`. CI builds the same image without pushing it.

## Licence

[MIT](LICENSE)
