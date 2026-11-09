# Skat architecture

## 1. Context and Scope

Skat serves a small circle of signed-in people in a browser. Outside it: the agents of the fleet, which play at Skat's `/mcp` under a token of their own (see Trust); the realm's identity provider (Keycloak), which signs people in, says who belongs to the Skat group and signs the agents' tokens, Skat's own Postgres database, which holds tables, chairs, dealt cards, auction steps, the declarer's steps, the cards played and command receipts, and the fleet's central legal pages at hallucinai.de, which the page links and which hal composes from each app's own part; Skat's part lives in `legal/` and hal reads it from each release. Skat builds on the fleet stack, FastAPI and Svelte with webauth for sign-in and appkit for the shared look, and takes a maintained library before writing its own code. Accounts and sessions are not in the database; they stay in memory.

```mermaid
flowchart LR
    person["Person's browser"] -->|"https: pages, /api/account and /api/tables"| skat["Skat"]
    person -->|"sign in"| keycloak["Keycloak"]
    agent["An agent of the fleet"] -->|"MCP tools at /mcp with its own token"| skat
    skat -->|"tables, chairs, hands, auction steps, declaring steps, played cards, receipts"| database[("Postgres")]
    skat -->|"code exchange, key set"| keycloak
    person -.->|"legal links"| legal["hallucinai.de legal pages"]
```

## 2. Building Block View

One process serves the static SvelteKit build and the few API routes. It refuses to start without the build and without a database at the newest migration.

```mermaid
flowchart TB
    subgraph browser["Browser"]
        pages["SvelteKit pages (adapter-static) with appkit"]
    end
    subgraph process["Skat process"]
        host["host: composition and server start"]
        web["web: webauth sign-in, session gate, security headers, routes, page build"]
        store["store: Postgres adapter, migrations"]
        table["table: records, rules, views, service"]
        engine["engine: Skat's own rules"]
        host --> web
        host --> store
        web --> table
        store --> table
    end
    pages --> web
```

- **`skat.host`** composes the app from settings and the page build, and starts uvicorn.
- **`skat.web`** is the adapter: webauth's sign-in routes and session gate, the security headers, the account routes, the table routes under `/api/tables`, `/health` and the page build, whose `/t/{id}` page opens a table by its link. It decides nobody's rights beyond admission. `web/mcp.py` owns the MCP front: it builds the protected resource and the front from agent-runtime's client library. Every route carries the mark of a tool or an exclusion with its reason, and an undecided route stops the build.
- **`skat.table`** is the table core: records, the rules that decide a command (a stand-up is refused while a hand runs), the views a person is allowed to see, and a service that runs each command as one transaction through a narrow port. Each phase of a hand is one module per layer (`table/auction.py`, `store/auction.py`, `web/auction.py`) with one short method on the command runner, and `HandProgress` holds what the phases recorded. Refusals have one owner per token: `Refusal` holds the table's own reasons and the engine's enums hold theirs, and one parser reads a stored token back. It imports no framework, driver or adapter.
- **`skat.engine`** holds Skat's own rules as pure code below the table. The table calls its deck, its deal and its bidding: the third sit draws the first dealer and deals the hand, a seated player's bid runs through the engine's auction, the declarer's steps through its declaration, every card through its tricks, and the tenth trick through its valuation and settlement. It imports no framework, driver or adapter.
- **`skat.store`** implements that port on Postgres with SQLAlchemy and psycopg 3, and owns the Alembic migrations. `skat migrate` takes an advisory lock and upgrades the database before any other setting or the page build is read; `skat serve` never migrates and refuses a database that is not at the newest migration. Migrations only expand. A table keeps its dealer in a column and its dealt hand in a card table with one row per card, whose key holds each card once per table and whose `holder` column names the position or the skat; the third sit stores both with its chair and receipt. The auction is `auction_actions`, one row per accepted step and ordinal, and the table reads it back by replaying the steps through the engine; a save whose stored steps are no prefix of the new ones raises, so an earlier step cannot be rewritten, and a stored log the engine refuses raises at the next command. The declarer's steps are `declaring_steps`, the same pattern with one row for a take, a put-back or a declaration; taking the skat changes no `hand_cards` row, and `save_table` raises when the hand it is given differs from the one dealt while the hand has progress, so the deal stays as dealt. The cards played are `played_cards`, one row per card and ordinal, with a unique key that holds each card once per table; the trick is derived from the ordinal and never stored, and the table replays the rows through the engine as well. The third pass and the thirtieth card are the two changes of the stored hand that do not raise while the hand has progress. The third pass ends the hand: its cards are deleted in that transaction, and its steps stay until the next deal replaces them, because the view between hands reads the passed-in fact from them. A hand passed in has no declarer, so it has no declaring steps. The thirtieth card ends a played hand: the record it leaves has no hand and empty progress, and its game joins the table's list, `TableRecord.game_list`, which outlives every deal and goes only with the table. `save_table` tells this end apart from a passed-in one by the longer list, and in that transaction one named step deletes the table's rows in `hand_cards`, `auction_actions`, `declaring_steps` and `played_cards` before `game_list` gains the new row. `game_list` is keyed by table and ordinal and holds the three seated accounts by seat with every number of the entry: the game's value and settlement from the engine, the bid from the auction and the declarer's points from the played tricks; a save whose list does not continue the stored one raises, as the step logs do. Every deal goes through one owner, `dealt` in the rules, which empties the hand's progress.
- Layer rule: `host` depends on `web` and `store`, which stand side by side and know nothing of each other, and both depend on `table`, and `engine` sits below `table`; never the other way. import-linter enforces it, and a second contract keeps `skat.table` and `skat.engine` free of SQLAlchemy, psycopg, FastAPI, Starlette, webauth, agent-runtime's client and the MCP SDK.
- **The frontend** (`frontend/`) is built to `src/skat/web/build`. The path constants it needs are generated from the Python constants.

## 3. Runtime View

```mermaid
sequenceDiagram
    participant B as Browser
    participant S as Skat
    participant K as Keycloak
    B->>S: open a page
    S-->>B: redirect to /login
    B->>S: follow the Log in link to /auth/start
    S-->>B: redirect to Keycloak with a pending-login cookie
    B->>K: sign in
    K-->>B: redirect to /auth/callback with a code
    B->>S: /auth/callback
    S->>K: exchange the code, fetch the key set
    alt member of the Skat group
        S-->>B: session cookie, redirect to the page
    else not admitted
        S-->>B: redirect to /no-access, no session
    end
    B->>S: open the page with the session
    S-->>B: start page, then GET /api/account for the name
```

An agent's tool call is one in-process request into the whole app. The agent presents its bearer token at `/mcp`; webauth's bearer gate admits it before routing, creates its own account (kind agent) on its first token, and the front answers `tools/list` and `tools/call` at revision 2026-07-28 alone. A call runs the marked route with the same token, so every middleware, the rate limit and the route's own checks apply as for a browser, and the route reads its actor from the admitted account. A refusal of the route comes back as a failed tool result with its reason.

Opening a table is one transaction: the service looks up the receipt under (account, command id), decides with a random 128-bit table id, writes the table with its opener in chair 1, its version and the receipt, and commits. The same command id with the same request returns the first table; another request under it is refused; two identical requests at once end with one table, because the receipt's key is unique and the loser's transaction rolls back and replays the winner's.

### The live view of a table

An open table page holds one server-sent-events stream (`GET /api/tables/{id}/events`, Starlette's streaming response). Admission is the session gate's at open, and an id that is no table is a plain 404 before anything is held open. A stream registers itself in `skat.web`'s in-memory presence registry, then reads and sends the full view built for its own account with `view_of`, then sends a fresh view after each change; no message names an account id or a watcher. The page shows the first view of a table it read once, then lets each message replace it.

- **Presence is process-local.** The registry keys connections per table and account, so an account in two tabs is one watcher; the count is the connected accounts without a chair. It lives only in this process, which is the one replica Skat runs as, and is never stored.
- **An away member's chair is freed by a timer per leave.** When an account's last stream on a table ends, presence records the leave on a monotonic clock and asks the event loop for one check after `SKAT_CHAIR_HOLD_SECONDS`; a returning stream clears the record. The check frees the chair only while that leave is still the account's latest, through `TableService.free_chair`, which runs off the event loop and wakes the table's streams after its commit. A failed freeing wakes nothing, is logged by error type and is checked again after a fixed delay until it commits. Leave times are not stored: at start, every occupied chair counts as just left, so a restart never frees a chair early and delays the freeing by at most one hold plus the outage. Shutdown cancels every pending check. The freeing's worker checks, once it holds the table's row, that the leave is still the latest and the server still runs, and a reconnect before that check keeps the chair; one after it awaits the commit on the event loop, never blocking it, and finds the chair freed. Shutdown starts no further freeing and waits, without blocking the event loop, for a write whose check already passed to end its transaction. A sweep would need a tick and free late, so the hold uses none.
- **The server frees a chair as a command with no actor.** `free_chair` locks the table's row, asks the same pure decision as standing up (the chair is freed only while the account still holds it and no hand runs), writes the chair and bumps the version in one transaction. It authorises nothing and writes no receipt: it carries no command id, and a repeat finds the chair already free and changes nothing. It and the next deal are the commands with no receipt. A member away when a hand ends gets a fresh hold: the ending command gives those without a connected stream a newer leave time before it commits, so a freeing that was already waiting for the row finds itself superseded, and the service returns who sat at the table, because a view carries no account id, so that after the commit the route hands those without a connected stream to the same hold; a retry of the ending command restarts none.
- **The next hand comes by itself after a passed-in hand.** When a command ends a hand, presence starts a table's pause from then, on the same timers as the chair hold; a pause still pending from an earlier hand is replaced and its timer does nothing when it fires, so a pending timer cannot shorten this one's. When a stream's first view finds a table passed in, presence starts a pause only if none is pending, so a stream opening during the pause neither cuts it short nor stretches it. When the pause ends, `TableService.deal_next` takes the table's row lock and deals only if the pure decision in `skat.table` holds on the locked row: no hand runs, the table has a dealer, all three chairs are occupied and all three occupants are connected at that moment, and while a played game's result is pending all three chairs are ready. Its worker reads who is connected once it holds the row, reads nobody once the server has stopped, and stays awaited by shutdown until its commit, so no deal is written after the stop. It draws through the one place a hand is drawn, bumps the version once and writes no receipt, and the streams wake after its commit; a repeat, or a table that changed meanwhile, changes nothing. A member who is away keeps their running hold, and their return opens a stream, which starts a fresh pause. A failed deal is logged by error type and changes nothing; the next stream opening asks again. No pause is stored: after a restart none is pending, and all three connected can only become true through streams opening, so no sweep is needed. A handler that dies between the last pass's commit and its scheduling heals only when a stream opens again.
- **After a played game, the next hand comes once all three have tapped „Weiter“.** Each chair stores its occupant's mark (`chairs.ready`, which a check keeps off a free chair). `POST /api/tables/{id}/ready` names the result the page saw by its number in the list and marks the actor's chair; a tap for another result is refused as `stale-result`, one with no result pending as `no-result`, and one from a chair already ready changes nothing and bumps no version, so a second tab's tap is no error. Whoever sits while a result is pending counts as ready, so that sit no longer deals at once; standing up, or a freed hold, takes only that chair's mark, and the one deal step clears every mark. After every accepted or replayed tap, after a sit during a pending result and on a stream's first view of a pending result, presence asks `deal_next` at once, with no pause, and the guard on the locked row decides: two taps that complete the marks serialise on the row lock, so the later deal finds a hand and does nothing; a member who is away delays the deal until their stream opens; a deal lost after its tap's commit follows the retry. Nothing of this lives in memory, so after a restart a pending result deals when the streams reopen, which every page does on load.
- **A command that changes a table is one locked transaction, then a publish.** A sit, a stand, an auction step, a declaring step, a played card or „Weiter“ locks the table's row with `SELECT … FOR UPDATE`, looks up its receipt under (account, command id), decides purely in `skat.table`, writes the change, bumps the version and stores the receipt, then commits. A read takes the same row's shared lock (`FOR SHARE`) instead, so a writer cannot commit between its statements and it sees one moment of the table. Two sits at one table therefore run one after the other: the loser's decision sees the chair taken and is refused with the holder's name, and a retry returns the stored outcome. An auction step, a declaring step or a played card also carries the version the client saw: a fresh command with an older one is refused as `stale-version`, while a retry is recognised by its receipt before that check. A replay reads its receipt's table under the shared lock too, except inside a command that already holds its own table's row and would otherwise risk a lock cycle with a command at the receipt's table. Only after the commit does the web layer wake the table's streams; a refused command wakes none.
- **A lost wake is recovered on the heartbeat.** A stream remembers the version it last sent. On each idle heartbeat it reads the view again and sends it only when the version has moved, so a committed change whose wake was lost reaches every stream within one heartbeat.
- **A wake carries no data.** An account appearing or disappearing at a table wakes the others with the version unchanged, and a lost wake of that kind is not recovered on the heartbeat, which sends only when the version moved. A wake is only a signal, so a stream that falls behind finds its wakes folded into one and reads the latest state, which is its fresh snapshot. A slow client never queues anything or delays another stream.
- **A stream re-admits its session.** Before each view it sends and on every idle heartbeat (`STREAM_HEARTBEAT_SECONDS`, the tick that also re-checks the version), it calls webauth's `admit_session` off the event loop, which also renews the session. A refusal ends the stream with nothing more sent; a store error ends it loudly. An ended session therefore stops receiving the table within one heartbeat.
- **A refused page signs in again.** When a stream ends, the page asks the table's session check. On a 401 it navigates to `/auth/start` with the table as `next` and a marker query, and returns to the table without a click while the issuer's own session lives; a refusal within a bounded window of loading a page that carries the marker reloads the table address, which the gate answers with the sign-in page, instead of navigating again. The marker is in the address, so the page keeps nothing on the device, and it removes the marker from the address once its first table request has been made. Checks run one at a time. Any other answer is a lost connection.
- **Shutdown ends the streams first.** uvicorn runs the lifespan shutdown only after it has waited for connections to close, so `StreamsEndingServer` (`skat.host.main`) stops the presence registry as shutdown begins: every open stream ends, and the wait finishes without cancelling anything or logging an error.
- **A lost connection** dims the page's last view and shows "verbinde neu" while the browser reconnects by itself; the first message of the new stream is a full view that replaces it.

Signing out is a POST to `/logout`: Skat ends the session and clears its cookies, and the person's browser posts the ID token hint to Keycloak's end-session endpoint, which returns to `/login`.

## 4. Deployment View

Skat runs live from the image the `Release` workflow pushes to `ghcr.io/overnightworks/skat`; CI builds the image from `Dockerfile` without pushing it.

## 5. Crosscutting Concepts

### Trust

The model is Skat's own.

- **A person's browser** controls everything it sends. Skat trusts only the session: the name shown comes from the Keycloak account, and a state-changing request needs same-origin provenance. HTTP requests are rate-limited per address, and the sign-in routes have their own budget; `/health` is exempt.
- **Anyone without a session** reaches only `/health`, the sign-in pages, the sign-in routes, the stylesheets and fonts those pages link, Keycloak's logout POST, and the public metadata document of `/mcp` at `/.well-known/oauth-protected-resource/mcp`. A forged, altered or expired session cookie counts as no session.
- **Keycloak** decides who is a member: the group `/apps/skat` admits, and no group makes anyone an admin. Skat trusts its signed tokens from the one configured issuer. The session store holds each login's ID token, a secret that leaves the server once, in the no-store logout page whose form the browser posts to Keycloak.
- **An agent** holds a token of its own that the realm signs for Skat's audience. webauth admits it only when the token carries the group `/agents` with an owner and a name, the group `/apps/skat/mcp` and the scope `mcp-skat`, and then the agent is its own account, never its owner's. The token is valid at `/mcp` and directly at the marked routes only; on every other route it is refused. At a marked route an admitted bearer skips the CSRF check and may carry an Origin; only `/mcp` refuses a token sent with an Origin, so no browser reaches it. A tool call replays the token, so the actor stays the agent and a client names no chair, seat or account. The realm alone decides which clients may mint Skat's audience; Skat adds no admission rule of its own.
- **The proxy hops** named in `SKAT_TRUSTED_PROXIES` are trusted to state the person's address in `X-Forwarded-For`; empty trusts none.
- **A table's id** is an unguessable link, not a secret: every signed-in member who has it sees the table. A client names only its retry key; the account and the chair always come from the session.
- **A table's cards** reach a viewer only through the view built for them: their own cards and the other chairs' counts, which are the cards still held while a game is played. A played card is public: it shows in the trick in progress and in the last completed trick. The declarer alone sees the skat, on picking it up and until two cards are put back; a Hand declarer never does; and an ouvert game's open cards, likewise the cards still held, are open to every viewer.
- **The operator's settings and secret files** are trusted fully. The two secrets and the database password come from files and never enter the environment; the database URL carries no password and comes from the environment, and a wrong setting is named, never echoed.

### Texts

`frontend/src/lib/catalogs/de.po` owns every visible Skat text. `scripts/generate_words.py` writes the typed `frontend/src/lib/words.ts` from it (`make words`; `make words-check`, part of `make lint`, fails on drift). A missing, empty or fuzzy translation fails the generator and a missing key fails the type check, so nothing fails at runtime. The sign-in pages keep appkit's English. A further language is one more catalog checked against `de.po`'s keys; choosing it is a later item.

### Proof strategy

Unit tests cover the logic and webauth's wiring through a test client with a fake issuer; the store's tests and the end-to-end tests run against a throwaway Postgres of the same major version as CI's service, migrated by Alembic, never SQLite. End-to-end tests drive real Chromium against a real server for sign-in, refusal, the start page, opening a table, watching it live and sign-out. Branch coverage is judged at 100 % over both together, merged with the frontend's.

## 6. Constraints and reasons

- Skat's markup holds no inline script, `<style>`, `style=` or `on*=` attribute: the page runs under webauth's content security policy, which admits only the SvelteKit bootstrap script and the route announcer's style by hash.
- The sign-in pages are prerendered with `csr = false`, so they carry no script.
- The Python path constants own the browser's paths, and `make wire` generates the TypeScript, so a drifting path fails `make wire-check` instead of showing at runtime.
- The test issuer exists only in tests and is never wired into the production composition.

## 7. Not chosen

- Skat's own sign-in: webauth is the fleet's one implementation of the session and admission rules; a need it cannot meet reopens it.

## 8. Risks and Technical Debt

- Accounts and sessions live in memory: a restart signs everyone out, and a second instance would not share them. An open table page comes back through the issuer by itself ("A refused page signs in again").
