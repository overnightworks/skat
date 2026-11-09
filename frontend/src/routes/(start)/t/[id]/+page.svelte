<script lang="ts">
    import { resolve } from "$app/paths";
    import { page } from "$app/state";
    import {
        auctionJustEnded,
        awayOnTurn,
        chairMarks,
        decidingMarks,
        decidingPlaque,
        PASSED_IN_MARKS,
        passedInScene,
    } from "#lib/auctionMarks.ts";
    import { bidLadder } from "#lib/bidLadder.ts";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { gameInPlay, sideNames, type PlayingHand } from "#lib/playView.ts";
    import { resultView, weiterBar } from "#lib/result.ts";
    import { LegalLinks } from "overnightworks-appkit";
    import BackFan from "#lib/ui/BackFan.svelte";
    import CardBack from "#lib/ui/CardBack.svelte";
    import DeclareControls from "#lib/ui/DeclareControls.svelte";
    import BidControls from "#lib/ui/BidControls.svelte";
    import FaceDownSkat from "#lib/ui/FaceDownSkat.svelte";
    import OwnHand from "#lib/ui/OwnHand.svelte";
    import PlayControls from "#lib/ui/PlayControls.svelte";
    import PlayedTrick from "#lib/ui/PlayedTrick.svelte";
    import ResultCard from "#lib/ui/ResultCard.svelte";
    import { ALL_POINTS } from "#lib/wire.ts";
    import SpeechBubble from "#lib/ui/SpeechBubble.svelte";
    import { words } from "#lib/words.ts";
    import NewTableButton from "../../NewTableButton.svelte";
    import {
        bidValueWhileDeclaring,
        copyTableLink,
        drawingOrder,
        gameWord,
        isSuitGame,
        markReady,
        positionWord,
        readTable,
        sitDown,
        standUp,
        takeAuctionStep,
        watchTable,
        type AuctionAction,
        type Outcome,
        type Picking,
        type Result,
        type Table,
    } from "../../tables.ts";

    const TAKEN_NOTICE_MILLISECONDS = 4000;
    const WON_MOMENT_MILLISECONDS = 2500;

    // The route has an [id] segment, so the parameter is always present.
    const id = $derived(page.params.id as string);
    let outcome = $state<Outcome | null>(null);
    let note = $state("");
    let taken: string | null = $state(null);
    let connected = $state(true);
    let picking = $state<Picking | undefined>();
    let playing = $state<PlayingHand | undefined>();
    // The first moment of the declaring, which only a page that sees the auction end shows.
    let justWon = $state(false);
    let wonTimer: ReturnType<typeof setTimeout> | undefined;

    function showTable(previous: Table, table: Table): void {
        if (auctionJustEnded(previous, table)) {
            justWon = true;
            clearTimeout(wonTimer);
            wonTimer = setTimeout(() => (justWon = false), WON_MOMENT_MILLISECONDS);
        }
        outcome = { kind: "table", table };
    }

    // SvelteKit keeps this component when the address changes from one table to another.
    $effect(() => {
        outcome = null;
        connected = true;
        justWon = false;
        let current = true;
        let stopWatching = (): void => {};
        void readTable(id).then((answer) => {
            if (!current) return;
            outcome = answer;
            if (answer.kind === "table") {
                let shown = answer.table;
                const show = (table: Table): void => {
                    showTable(shown, table);
                    shown = table;
                };
                stopWatching = watchTable(id, show, (isConnected) => (connected = isConnected));
            }
        });
        // An answer for an address the person has left must not replace the current table.
        return () => {
            current = false;
            clearTimeout(wonTimer);
            stopWatching();
        };
    });

    const seated = $derived(outcome?.kind === "table" && outcome.table.chairs.some((chair) => chair.is_mine));
    const ownTurnLadder = $derived.by(() => {
        if (outcome?.kind !== "table" || outcome.table.hand === null) return null;
        const viewerSeat = outcome.table.chairs.find((chair) => chair.is_mine)?.seat;
        return bidLadder(outcome.table.hand.auction, viewerSeat);
    });
    // The version a step was sent from: the controls stay off until a newer version arrives or the step fails.
    let sentFromVersion: number | null = $state(null);

    async function copy(): Promise<void> {
        note = (await copyTableLink(id)) ? words.linkCopied : words.linkCopyFailed;
    }

    // A seated or freed chair reaches this page through its stream like every other page's: the answer's table
    // is not the streamed view, so it never replaces it.
    let takenTimer: ReturnType<typeof setTimeout> | undefined;

    async function seat(command: Promise<Outcome>): Promise<Outcome> {
        note = "";
        taken = null;
        const answer = await command;
        if (answer.kind === "taken") {
            taken = answer.holder;
            clearTimeout(takenTimer);
            takenTimer = setTimeout(() => (taken = null), TAKEN_NOTICE_MILLISECONDS);
        } else if (answer.kind !== "table") {
            note = words.commandFailed;
        }
        return answer;
    }

    // „Weiter“ names the result on the page; the button stays busy until the stream brings a newer version.
    async function tapWeiter(table: Table): Promise<void> {
        sentFromVersion = table.version;
        const answer = await seat(markReady(id, crypto.randomUUID(), (table.result as Result).ordinal));
        if (answer.kind !== "table") sentFromVersion = null;
    }

    async function takeStep(table: Table, action: AuctionAction, value?: number): Promise<void> {
        sentFromVersion = table.version;
        const answer = await seat(takeAuctionStep(id, crypto.randomUUID(), table.version, action, value));
        if (answer.kind !== "table") sentFromVersion = null;
    }
</script>

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
    <title>{`${words.appName}`}</title>
</svelte:head>

<div class="room" data-theme="dark">
    <!-- Kept out of layout with zero size: display:none would break the gradient references in Chrome. -->
    <svg class="sprite" width="0" height="0" aria-hidden="true">
        <defs>
            <symbol id="suit-kreuz" viewBox="0 0 100 100">
                <circle cx="50" cy="28" r="19" />
                <circle cx="27" cy="58" r="19" />
                <circle cx="73" cy="58" r="19" />
                <circle cx="50" cy="52" r="12" />
                <path d="M45 58C45 77 40 88 30 96H70C60 88 55 77 55 58Z" />
            </symbol>
            <symbol id="suit-pik" viewBox="0 0 100 100">
                <path
                    d="M50 4C62 26 93 40 93 63C93 77 82 85 70 85C62 85 56 81 53 75C54 85 58 92 67 96H33C42 92 46 85 47 75C44 81 38 85 30 85C18 85 7 77 7 63C7 40 38 26 50 4Z"
                />
            </symbol>
            <symbol id="suit-herz" viewBox="0 0 100 100">
                <path
                    d="M50 92C22 69 5 52 5 32C5 17 16 7 30 7C39 7 46 12 50 21C54 12 61 7 70 7C84 7 95 17 95 32C95 52 78 69 50 92Z"
                />
            </symbol>
            <symbol id="suit-karo" viewBox="0 0 100 100">
                <path d="M50 3Q68 29 90 50Q68 71 50 97Q32 71 10 50Q32 29 50 3Z" />
            </symbol>
            <symbol id="court-king" viewBox="0 0 100 70">
                <path d="M14 52L8 14L32 34L50 6L68 34L92 14L86 52Z" />
                <rect x="14" y="56" width="72" height="9" rx="3" />
                <circle cx="8" cy="12" r="5" />
                <circle cx="50" cy="5" r="5" />
                <circle cx="92" cy="12" r="5" />
            </symbol>
            <symbol id="court-queen" viewBox="0 0 100 70">
                <path d="M10 60Q50 8 90 60Q50 42 10 60Z" />
                <circle cx="50" cy="20" r="7" />
                <circle cx="27" cy="38" r="5" />
                <circle cx="73" cy="38" r="5" />
                <rect x="10" y="60" width="80" height="6" rx="3" />
            </symbol>
            <symbol id="court-jack" viewBox="0 0 100 70">
                <path d="M12 62Q22 30 52 28Q80 28 88 62Z" />
                <path d="M58 30Q70 6 96 2Q86 18 66 36Z" />
                <rect x="10" y="60" width="80" height="7" rx="3" />
            </symbol>
            <linearGradient id="card-fill" x1="0" y1="0" x2=".4" y2="1">
                <stop offset="0" stop-color="#fffdf7" />
                <stop offset="1" stop-color="#efe9da" />
            </linearGradient>
            <linearGradient id="court-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#fbf3df" />
                <stop offset="1" stop-color="#f1e4c4" />
            </linearGradient>
        </defs>
    </svg>
    <header class="bar" class:stale={!connected}>
        <a class="wordmark" href={resolve("/(start)")}>{words.appName}</a>
        {#if outcome?.kind === "table"}
            <div class="watchers" title={words.watchers} role="group" aria-label={words.watchers}>
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                >
                    <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
                    <circle cx="12" cy="12" r="3" />
                </svg>
                <span>{outcome.table.watchers}</span>
            </div>
        {/if}
    </header>
    <main class="stage" class:stale={!connected}>
        {#if outcome?.kind === "table"}
            {@const ownCards = outcome.table.hand?.own_cards ?? []}
            <!-- A chair waits only on a seated viewer, and a seated viewer's chair always carries their name. -->
            {@const ownChair = outcome.table.chairs.find((chair) => chair.is_mine)}
            {@const ownInitial = String(ownChair?.occupant_name).slice(0, 1)}
            {@const bidValue = bidValueWhileDeclaring(outcome.table)}
            {@const inPlay = gameInPlay(outcome.table)}
            {@const turnSeat = inPlay?.playing.turn_seat}
            {@const settledDeclarerSeat = outcome.table.result?.declarer_seat ?? inPlay?.declarerSeat}
            {@const view = outcome.table.result === null ? null : resultView(outcome.table)}
            {@const winners = new Set(view?.rows.filter((row) => row.winner).map((row) => row.seat))}
            {@const bar = weiterBar(outcome.table)}
            {@const passedIn = passedInScene(outcome.table.passed_in, outcome.table.chairs)}
            {@const deciding = decidingPlaque(outcome.table, justWon)}
            {#if view !== null}
                <!-- The card carries the game and the points, so the plaque stays out while a result stands. -->
            {:else if deciding !== null}
                <div class="plaque deciding">
                    {#if deciding.kind === "won"}
                        <span>{`${deciding.name} ${words.plays}, ${String(deciding.value)}`}</span>
                    {:else}
                        <span>{`${words.bidValue} ${String(deciding.value)}`}</span>
                        <span class="gives">
                            {`${deciding.name} ${deciding.kind === "choosing" ? words.chooses : words.discards}`}
                            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                        </span>
                    {/if}
                </div>
            {:else if bidValue !== null}
                <div class="plaque">
                    <span>{`${words.bidValue} ${String(bidValue)}`}</span>
                </div>
            {:else if inPlay !== null}
                {@const names = sideNames(outcome.table.chairs, inPlay.declarerSeat)}
                {@const points = inPlay.playing.trick_points}
                <div class="plaque in-play">
                    <span class="game">
                        {#if isSuitGame(inPlay.game)}
                            <span class={`suit ${inPlay.game}`} aria-hidden="true">
                                <svg viewBox="0 0 100 100"><use href={`#suit-${inPlay.game}`} /></svg>
                            </span>
                        {/if}
                        {gameWord(inPlay.game)}
                    </span>
                    <div class="points" role="group" aria-label={words.trickPoints}>
                        <span class="sides">
                            <span class="declarer">{`${names.declarer} ${String(points.declarer)}`}</span>
                            <span class="opponents">{`${names.opponents} ${String(points.opponents)}`}</span>
                        </span>
                        <span class="track">
                            <svg viewBox={`0 0 ${String(ALL_POINTS)} 1`} preserveAspectRatio="none" aria-hidden="true">
                                <rect class="declarer" width={points.declarer} height="1" />
                                <rect
                                    class="opponents"
                                    x={ALL_POINTS - points.opponents}
                                    width={points.opponents}
                                    height="1"
                                />
                            </svg>
                            <i class="win-line"></i>
                        </span>
                    </div>
                </div>
            {:else if !outcome.table.hand?.declaring}
                {@const awayName = outcome.table.hand && awayOnTurn(outcome.table.hand.auction, outcome.table.chairs)}
                <div class="plaque" class:hand-over={passedIn !== null}>
                    {#if passedIn !== null}
                        <span class="verdict">{words.passedIn}</span>
                        {#if passedIn.dealerName !== null}
                            <span class="gives">
                                {`${passedIn.dealerName} ${words.gives}`}
                                <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                            </span>
                        {/if}
                    {:else if outcome.table.hand === null}
                        <span>{words.waitingForPlayers}</span>
                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                    {:else if awayName}
                        <span>{`${words.waitingFor} ${awayName}`}</span>
                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                    {:else}
                        <span>{words.bidding}</span>
                    {/if}
                </div>
            {/if}
            <div class="felt" aria-hidden="true"></div>
            {#if view !== null}
                <ResultCard {view} />
            {/if}
            {#if inPlay !== null}
                <PlayedTrick chairs={outcome.table.chairs} playing={inPlay.playing} />
            {/if}
            {@const dealerSeat = passedIn?.dealerSeat ?? outcome.table.hand?.dealer_seat}
            {@const auction = outcome.table.hand?.auction}
            {@const declaring = outcome.table.hand?.declaring}
            {#if outcome.table.hand !== null && inPlay === null}
                <div class="skat-spot">
                    <FaceDownSkat count={outcome.table.hand.skat_count} />
                </div>
            {:else if passedIn !== null}
                <div class="skat-spot">
                    <div class="deck">
                        {#each [0, 1, 2, 3] as layer (layer)}
                            <div class="deck-card">
                                <CardBack />
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
            <ul class="chairs">
                {#each drawingOrder(outcome.table.chairs) as chair (chair.seat)}
                    {@const marks =
                        passedIn !== null
                            ? PASSED_IN_MARKS
                            : declaring
                              ? decidingMarks(declaring, chair.seat, justWon)
                              : chairMarks(auction, chair.seat, ownChair?.seat)}
                    <li
                        class="chair"
                        class:mine={chair.is_mine}
                        class:away={chair.is_away}
                        class:out={marks.passed}
                        class:win={winners.has(chair.seat)}
                        class:turn={marks.turn || chair.seat === turnSeat}
                        data-seat={chair.seat}
                    >
                        {#if chair.occupant_name !== null}
                            <span class="tile">
                                <span class="initial" aria-hidden="true">{chair.occupant_name.slice(0, 1)}</span>
                            </span>
                            {#if chair.hand !== null || passedIn !== null || view !== null}
                                {#if chair.seat === dealerSeat}
                                    <span class="mark dealer" title={words.dealer}>
                                        <svg
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            stroke-width="2"
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            aria-hidden="true"
                                        >
                                            <path
                                                d="M3 7h3c4.5 0 6.5 10 11 10h3.5M3 17h3c1.7 0 3-1.4 4.1-3.4M13.9 10.4C15 8.4 16.3 7 18 7h2.5M18 4l3 3-3 3M18 14l3 3-3 3"
                                            />
                                        </svg>
                                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                                        {`${words.dealer}`}
                                    </span>
                                {/if}
                                {#if chair.hand !== null}
                                    <span class="mark pos">{positionWord(chair.hand.position)}</span>
                                {/if}
                                {#if marks.declarer || chair.seat === settledDeclarerSeat}
                                    <span class="mark declarer" class:won={marks.declarer === "won"}>
                                        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                            <path
                                                d="M12 2.5l2.9 6.2 6.8.8-5 4.7 1.3 6.7L12 17.5 6 20.9l1.3-6.7-5-4.7 6.8-.8z"
                                            />
                                        </svg>
                                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                                        {`${words.plays}`}
                                    </span>
                                {/if}
                                {#if marks.turn || chair.seat === turnSeat}
                                    <span class="mark turn" aria-hidden="true">
                                        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                            <path d="M8 5l11 7-11 7z" />
                                        </svg>
                                    </span>
                                {:else if marks.passed}
                                    <span class="mark pass">
                                        <svg
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            stroke-width="2.8"
                                            stroke-linecap="round"
                                            aria-hidden="true"
                                        >
                                            <path d="M6 6l12 12M18 6L6 18" />
                                        </svg>
                                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                                        {`${words.pass}`}
                                    </span>
                                {:else if marks.waits}
                                    <span class="mark waits" title={words.waitsForYou}>
                                        <span class="dot" aria-hidden="true">{ownInitial}</span>
                                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                                    </span>
                                {/if}
                                {#if marks.bubble}
                                    <SpeechBubble bubble={marks.bubble} initial={chair.occupant_name.slice(0, 1)} />
                                {/if}
                            {/if}
                            {#if view !== null}
                                {#if chair.ready}
                                    <span class="mark ready" title={words.readyMark}>
                                        <svg
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            stroke-width="3"
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            aria-hidden="true"
                                        >
                                            <path d="M5 12.5l4.5 4.5L19 7" />
                                        </svg>
                                    </span>
                                {:else}
                                    <span class="mark waits" title={words.notReadyMark}>
                                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                                    </span>
                                {/if}
                            {/if}
                            {#if chair.is_away}
                                <span class="mark away" aria-hidden="true">
                                    <svg
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        stroke-width="2"
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                    >
                                        <path d="M19.5 14.6A7.8 7.8 0 1 1 9.4 4.5a6.3 6.3 0 0 0 10.1 10.1z" />
                                    </svg>
                                </span>
                            {/if}
                        {:else if seated}
                            <span class="tile empty"></span>
                        {:else}
                            <button
                                type="button"
                                class="tile empty free"
                                aria-label={words.sitDown}
                                onclick={() => seat(sitDown(id, chair.seat, crypto.randomUUID()))}
                            >
                                <svg
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    stroke-width="2.2"
                                    stroke-linecap="round"
                                    aria-hidden="true"
                                >
                                    <path d="M12 5v14M5 12h14" />
                                </svg>
                            </button>
                        {/if}
                        <span class="plate"
                            >{chair.occupant_name ?? words.seatFree}{#if chair.is_away}<small class="away-note"
                                    >{words.seatAway}</small
                                >{/if}</span
                        >
                        {#if chair.hand !== null}
                            {#if !chair.is_mine}
                                <div class="fan-spot">
                                    <BackFan count={chair.hand.card_count} dim={chair.is_away} />
                                </div>
                            {/if}
                            {#if !chair.is_mine}
                                <span class="count-tag" title={words.cardCount}>
                                    <svg
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        stroke-width="2"
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        aria-hidden="true"
                                    >
                                        <rect x="3" y="7" width="11" height="14.5" rx="2" />
                                        <path
                                            d="M8 7V4.5A1.5 1.5 0 0 1 9.5 3h10A1.5 1.5 0 0 1 21 4.5v12a1.5 1.5 0 0 1-1.5 1.5H14"
                                        />
                                    </svg>
                                    <span>{chair.hand.card_count}</span>
                                </span>
                            {/if}
                        {/if}
                    </li>
                {/each}
            </ul>
            <DeclareControls {id} table={outcome.table} bind:picking bind:note />
            <PlayControls {id} table={outcome.table} bind:playing bind:note />
            {#if ownTurnLadder !== null}
                {@const table = outcome.table}
                <BidControls
                    ladder={ownTurnLadder}
                    disabled={sentFromVersion === table.version}
                    onstep={(action: AuctionAction, value?: number) => {
                        void takeStep(table, action, value);
                    }}
                />
            {/if}
            <div class="controls">
                {#if ownCards.length > 0}
                    <OwnHand cards={ownCards} {picking} {playing} />
                {/if}
                <div class="actions" class:on-result={view !== null}>
                    {#if bar?.kind === "tap"}
                        {@const table = outcome.table}
                        <button
                            type="button"
                            class="copy weiter"
                            disabled={sentFromVersion === table.version && !bar.again}
                            onclick={() => tapWeiter(table)}
                        >
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="3"
                                stroke-linecap="round"
                                stroke-linejoin="round"
                                aria-hidden="true"
                            >
                                <path d="M5 12.5l4.5 4.5L19 7" />
                            </svg>
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                            {`${words.weiter}`}
                        </button>
                    {:else if bar !== null}
                        <span class="copy wait" role="status">
                            {`${words.waitingFor} ${bar.names}`}
                            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                        </span>
                    {/if}
                    {#if seated && outcome.table.hand === null}
                        <button type="button" class="copy" onclick={() => seat(standUp(id, crypto.randomUUID()))}>
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                                stroke-linecap="round"
                                stroke-linejoin="round"
                                aria-hidden="true"
                            >
                                <path d="M4.5 4v16M4.5 13.5h8.5v6.5" />
                                <path d="M18.5 15V4M15 7.5l3.5-3.5L22 7.5" />
                            </svg>
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                            {`${words.standUp}`}
                        </button>
                    {/if}
                    <button type="button" class="copy link" aria-label={words.copyLink} onclick={copy}>
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            aria-hidden="true"
                        >
                            <path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2" />
                            <path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2" />
                        </svg>
                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                        <span class="label">{`${words.copyLink}`}</span>
                    </button>
                </div>
                <p class="note" role="status">{note}</p>
            </div>
            {#if taken !== null}
                <p class="notice" role="status">
                    <span class="dot" aria-hidden="true">{taken.slice(0, 1)}</span>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                    <span class="label">{`${words.seatTaken}`}</span>
                    <b>{taken}</b>
                </p>
            {/if}
        {:else if outcome?.kind === "missing"}
            <section class="panel">
                <h1>{words.tableNotFound}</h1>
                <NewTableButton />
            </section>
        {:else if outcome?.kind === "failed"}
            <section class="panel" role="alert">
                <h1>{words.tableLoadFailed}</h1>
                <p>{words.tableLoadFailedHint}</p>
            </section>
        {/if}
    </main>
    <div class="reconnect" role="status" hidden={connected}><span class="spin"></span>{words.reconnecting}</div>
    <footer class="legal">
        <LegalLinks links={LEGAL_LINKS} />
    </footer>
</div>
