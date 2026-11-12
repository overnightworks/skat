<script lang="ts">
    import { onMount, untrack } from "svelte";
    import { resolve } from "$app/paths";
    import { page } from "$app/state";
    import {
        awayOnTurn,
        chairMarks,
        decidingMarks,
        decidingPlaque,
        PASSED_IN_MARKS,
        passedInScene,
    } from "#lib/auctionMarks.ts";
    import { bidLadder } from "#lib/bidLadder.ts";
    import { cuesBetween } from "#lib/cues.ts";
    import { greetCall, isFramedInCallMode } from "#lib/callFrame.ts";
    import { giveUpView } from "#lib/giveUp.ts";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { gameInPlay, type PlayingHand } from "#lib/playView.ts";
    import { declaredResult, ramschResultView, resultView, weiterBar, withMinus } from "#lib/result.ts";
    import { AiMark, LegalLinks } from "overnightworks-design";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";
    import AgentsPill from "#lib/ui/AgentsPill.svelte";
    import BackFan from "#lib/ui/BackFan.svelte";
    import OpenHand from "#lib/ui/OpenHand.svelte";
    import CardBack from "#lib/ui/CardBack.svelte";
    import DeclareControls from "#lib/ui/DeclareControls.svelte";
    import BidControls from "#lib/ui/BidControls.svelte";
    import FaceDownSkat from "#lib/ui/FaceDownSkat.svelte";
    import GiveUpPlaque from "#lib/ui/GiveUpPlaque.svelte";
    import OwnHand from "#lib/ui/OwnHand.svelte";
    import PlayControls from "#lib/ui/PlayControls.svelte";
    import PlayedTrick from "#lib/ui/PlayedTrick.svelte";
    import RamschResultCard from "#lib/ui/RamschResultCard.svelte";
    import ResultCard from "#lib/ui/ResultCard.svelte";
    import SoundButton from "#lib/ui/SoundButton.svelte";
    import SpeechBubble from "#lib/ui/SpeechBubble.svelte";
    import { armSound, soundForCues } from "#lib/tableSound.ts";
    import { words } from "#lib/words.ts";
    import TableClosed from "./TableClosed.svelte";
    import {
        agentSitsNote,
        answerGiveUp,
        bidValueWhileDeclaring,
        copyTableLink,
        drawingOrder,
        gameLabel,
        isSuitGame,
        markReady,
        positionWord,
        readTable,
        sitDown,
        standUp,
        takeAuctionStep,
        watchTable,
        type AuctionAction,
        type Card,
        type GiveUpAnswer,
        type Outcome,
        type Picking,
        type Table,
    } from "../../tables.ts";

    const TAKEN_NOTICE_MILLISECONDS = 4000;
    const WON_MOMENT_MILLISECONDS = 2500;
    const AGENT_SITS_MILLISECONDS = 4000;

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
    // The cards this page saw laid in the running hand; a card that was not seen laid, a reload's for one, is not here.
    let playedThisHand = $state<Card[]>([]);
    let wonTimer: ReturnType<typeof setTimeout> | undefined;
    // The version of the latest streamed table, which the control that calls agents follows.
    let streamedVersion = $state<number | null>(null);
    // The sentence that names the agent who has just sat down.
    let agentSat = $state<string | null>(null);
    let agentSatTimer: ReturnType<typeof setTimeout> | undefined;

    function showTable(previous: Table | undefined, table: Table): void {
        streamedVersion = table.version;
        const sitsNote = previous === undefined ? null : agentSitsNote(previous, table);
        if (sitsNote !== null) {
            agentSat = sitsNote;
            clearTimeout(agentSatTimer);
            agentSatTimer = setTimeout(() => (agentSat = null), AGENT_SITS_MILLISECONDS);
        }
        if (table.hand?.dealer_seat !== previous?.hand?.dealer_seat) playedThisHand = [];
        const cues = cuesBetween(previous, table);
        soundForCues(cues, table);
        for (const cue of cues) {
            if (cue.kind === "card-played") {
                playedThisHand = [...playedThisHand, cue.card];
            } else {
                justWon = true;
                clearTimeout(wonTimer);
                wonTimer = setTimeout(() => (justWon = false), WON_MOMENT_MILLISECONDS);
            }
        }
        outcome = { kind: "table", table };
    }

    // SvelteKit keeps this component when the address changes from one table to another.
    $effect(() => {
        outcome = null;
        connected = true;
        justWon = false;
        streamedVersion = null;
        agentSat = null;
        playedThisHand = [];
        let current = true;
        let stopWatching = (): void => {};
        void readTable(id).then((answer) => {
            if (!current) return;
            outcome = answer;
            if (answer.kind === "table" && answer.table.ended === null) {
                let shown: Table | undefined = answer.table;
                const show = (table: Table): void => {
                    showTable(shown, table);
                    shown = table;
                };
                // A dropped connection forgets the table shown: the first table after it stands still.
                stopWatching = watchTable(id, show, (isConnected) => {
                    connected = isConnected;
                    if (!isConnected) shown = undefined;
                });
            }
        });
        // An answer for an address the person has left must not replace the current table.
        return () => {
            current = false;
            clearTimeout(wonTimer);
            clearTimeout(agentSatTimer);
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

    const callMode = isFramedInCallMode();
    // The call's first valid greeting takes Skat's own bar away; a call that never greets leaves it.
    let greeted = $state(false);
    onMount(armSound);
    onMount(() => {
        if (!callMode) return;
        return greetCall(
            untrack(() => id),
            {
                parent: window.parent,
                fetch: (path) => fetch(path),
                post: (message, targetOrigin) => {
                    window.parent.postMessage(message, targetOrigin);
                },
                listen: (handler) => {
                    window.addEventListener("message", handler);
                    return () => {
                        window.removeEventListener("message", handler);
                    };
                },
            },
            () => {
                greeted = true;
            },
        );
    });

    async function copy(): Promise<void> {
        note = (await copyTableLink(id)) ? words["table.linkCopied"] : words["table.linkCopyFailed"];
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
            note = words["table.commandFailed"];
        }
        return answer;
    }

    // „Weiter“ names the result on the page; the button stays busy until the stream brings a newer version.
    async function tapWeiter(table: Table): Promise<void> {
        sentFromVersion = table.version;
        const answer = await seat(
            markReady(id, crypto.randomUUID(), (table.result as NonNullable<Table["result"]>).ordinal),
        );
        if (answer.kind !== "table") sentFromVersion = null;
    }

    async function answerRequest(table: Table, answer: GiveUpAnswer): Promise<void> {
        sentFromVersion = table.version;
        const reply = await seat(answerGiveUp(id, table.version, crypto.randomUUID(), answer));
        if (reply.kind !== "table") sentFromVersion = null;
    }

    async function takeStep(table: Table, action: AuctionAction, value?: number): Promise<void> {
        sentFromVersion = table.version;
        const answer = await seat(takeAuctionStep(id, crypto.randomUUID(), table.version, action, value));
        if (answer.kind !== "table") sentFromVersion = null;
    }
</script>

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    <title>{`${words["app.name"]}`}</title>
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
    {#if !greeted}
        <header class="bar">
            {#if callMode}
                <span class="wordmark" class:stale={!connected}>{words["app.name"]}</span>
            {:else}
                <a
                    class="lobby"
                    href={resolve("/(start)")}
                    title={words["table.lobby"]}
                    aria-label={words["table.lobby"]}
                >
                    <span class="lobby-face button-glass">
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            aria-hidden="true"
                        >
                            <path d="M4 11.5 12 5l8 6.5" />
                            <path d="M6.5 10v9h11v-9" />
                        </svg>
                        <span class="lobby-word">{words["table.lobby"]}</span>
                    </span>
                </a>
            {/if}
            {#if outcome?.kind === "table" && outcome.table.ended === null}
                {#if !callMode}
                    <SoundButton place="bar" />
                {/if}
                <div
                    class="watchers"
                    class:stale={!connected}
                    title={words["table.watchers"]}
                    role="group"
                    aria-label={words["table.watchers"]}
                >
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
    {/if}
    <main class="stage" class:stale={!connected} class:after-drop={greeted}>
        {#if outcome?.kind === "table" && outcome.table.ended !== null}
            <TableClosed ended={outcome.table.ended} />
        {:else if outcome?.kind === "table"}
            {@const ownCards = outcome.table.hand?.own_cards ?? []}
            <!-- A chair waits only on a seated viewer, and a seated viewer's chair always carries their name. -->
            {@const ownChair = outcome.table.chairs.find((chair) => chair.is_mine)}
            {@const ownInitial = String(ownChair?.occupant_name).slice(0, 1)}
            {@const bidValue = bidValueWhileDeclaring(outcome.table)}
            {@const inPlay = gameInPlay(outcome.table)}
            {@const declared = declaredResult(outcome.table)}
            {@const view = declared === null ? null : resultView(outcome.table)}
            {@const ramschView = ramschResultView(outcome.table)}
            {@const onResult = view !== null || ramschView !== null}
            {@const winners = new Set((view ?? ramschView)?.rows.filter((row) => row.won).map((row) => row.seat))}
            {@const bar = weiterBar(outcome.table)}
            {@const passedIn = passedInScene(outcome.table.passed_in, outcome.table.chairs)}
            {@const deciding = decidingPlaque(outcome.table, justWon)}
            {@const giveUp = giveUpView(outcome.table)}
            {#if onResult}
                <!-- The card carries the game and the points, so the plaque stays out while a result stands. -->
            {:else if deciding !== null}
                <div class="plaque deciding">
                    {#if deciding.kind === "won"}
                        <span>{`${deciding.name} ${words["table.plays"]}, ${String(deciding.value)}`}</span>
                    {:else}
                        <span>{`${words["table.bidValue"]} ${String(deciding.value)}`}</span>
                        <span class="gives">
                            {`${deciding.name} ${deciding.kind === "choosing" ? words["table.chooses"] : words["table.discards"]}`}
                            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                        </span>
                    {/if}
                </div>
            {:else if bidValue !== null}
                <div class="plaque">
                    <span>{`${words["table.bidValue"]} ${String(bidValue)}`}</span>
                </div>
            {:else if inPlay !== null}
                {@const label = gameLabel(inPlay.declaration)}
                {#if giveUp !== null}
                    {@const table = outcome.table}
                    <GiveUpPlaque
                        view={giveUp}
                        disabled={sentFromVersion === table.version}
                        onanswer={(answer: GiveUpAnswer) => {
                            void answerRequest(table, answer);
                        }}
                    />
                {:else}
                    <div class="plaque" class:wide={label.announcement !== null}>
                        <span class="game">
                            {#if isSuitGame(inPlay.declaration.game)}
                                <span class={`suit ${inPlay.declaration.game}`} aria-hidden="true">
                                    <svg viewBox="0 0 100 100"><use href={`#suit-${inPlay.declaration.game}`} /></svg>
                                </span>
                            {/if}
                            {label.name}
                            {#if label.announcement !== null}
                                <span class="announced">{label.announcement}</span>
                            {/if}
                        </span>
                    </div>
                {/if}
            {:else if !outcome.table.hand?.declaring}
                {@const awayName = outcome.table.hand && awayOnTurn(outcome.table.hand.auction, outcome.table.chairs)}
                <div class="plaque" class:hand-over={passedIn !== null}>
                    {#if passedIn !== null}
                        <span class="verdict">{words["table.passedIn"]}</span>
                        {#if passedIn.dealerName !== null}
                            <span class="gives">
                                {`${passedIn.dealerName} ${words["table.gives"]}`}
                                <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                            </span>
                        {/if}
                    {:else if outcome.table.hand === null}
                        <span>{words["table.waitingForPlayers"]}</span>
                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                    {:else if awayName}
                        <span>{`${words["table.waitingFor"]} ${awayName}`}</span>
                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                    {:else}
                        <span>{words["table.bidding"]}</span>
                    {/if}
                </div>
            {/if}
            <div class="felt" aria-hidden="true"></div>
            {#if view !== null}
                <ResultCard {view} />
            {:else if ramschView !== null}
                <RamschResultCard view={ramschView} />
            {/if}
            {#if inPlay !== null}
                <PlayedTrick chairs={outcome.table.chairs} playing={inPlay.playing} {playedThisHand} />
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
                    {@const openCards = chair.seat === declaring?.declarer_seat ? declaring.open_cards : []}
                    <li
                        class="chair"
                        class:mine={chair.is_mine}
                        class:away={chair.is_away}
                        class:out={marks.passed}
                        class:win={winners.has(chair.seat)}
                        class:turn={marks.turn || chair.seat === inPlay?.playing.turn_seat}
                        data-seat={chair.seat}
                    >
                        {#if chair.occupant_name !== null}
                            <span class="tile" class:agent={chair.occupant_kind === "agent"}>
                                {#if chair.occupant_kind === "agent"}
                                    <span class="orb" aria-hidden="true">
                                        <AgentSparkle />
                                    </span>
                                {:else}
                                    <span class="initial" aria-hidden="true">{chair.occupant_name.slice(0, 1)}</span>
                                {/if}
                            </span>
                            {#if chair.hand !== null || passedIn !== null || onResult}
                                {#if chair.seat === dealerSeat}
                                    <span class="mark dealer" title={words["table.dealer"]}>
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
                                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                                        {`${words["table.dealer"]}`}
                                    </span>
                                {/if}
                                {#if chair.hand !== null}
                                    <span class="mark pos">{positionWord(chair.hand.position)}</span>
                                {/if}
                                {#if marks.declarer || chair.seat === (declared?.declarer_seat ?? inPlay?.declarerSeat)}
                                    <span class="mark declarer" class:won={marks.declarer === "won"}>
                                        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                            <path
                                                d="M12 2.5l2.9 6.2 6.8.8-5 4.7 1.3 6.7L12 17.5 6 20.9l1.3-6.7-5-4.7 6.8-.8z"
                                            />
                                        </svg>
                                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                                        {`${words["table.plays"]}`}
                                    </span>
                                {/if}
                                {#if giveUp?.marks.get(chair.seat) === "declined"}
                                    <span class="mark declined" title={words["table.saidNo"]}>
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
                                    </span>
                                {/if}
                                {#if giveUp?.marks.get(chair.seat) === "unanswered"}
                                    <span class="mark unanswered" title={words["table.noAnswerYet"]}>
                                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                                    </span>
                                {/if}
                                {#if marks.turn || chair.seat === inPlay?.playing.turn_seat}
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
                                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                                        {`${words["table.pass"]}`}
                                    </span>
                                {:else if marks.waits}
                                    <span class="mark waits" title={words["table.waitsForYou"]}>
                                        <span class="dot" aria-hidden="true">{ownInitial}</span>
                                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                                    </span>
                                {/if}
                                {#if marks.bubble}
                                    <SpeechBubble bubble={marks.bubble} initial={chair.occupant_name.slice(0, 1)} />
                                {/if}
                            {/if}
                            {#if onResult}
                                {#if chair.ready}
                                    <span class="mark ready" title={words["table.readyMark"]}>
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
                                    <span class="mark waits" title={words["table.notReadyMark"]}>
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
                                aria-label={words["table.sitDown"]}
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
                            >{chair.is_mine
                                ? words["table.sideYou"]
                                : (chair.occupant_name ??
                                  words["table.seatFree"])}{#if chair.occupant_kind === "agent"}<AiMark
                                />{/if}{#if chair.is_away}<small class="away-note">{words["table.seatAway"]}</small
                                >{/if}</span
                        >
                        {#if chair.total !== null}
                            <span class="coaster">{withMinus(chair.total)}</span>
                        {/if}
                        {#if chair.hand !== null}
                            {#if openCards.length > 0}
                                {#if chair.is_mine}
                                    <span class="open-tag" title={words["table.openForAll"]}>
                                        <svg
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            stroke-width="2"
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            aria-hidden="true"
                                        >
                                            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
                                            <circle cx="12" cy="12" r="3" />
                                        </svg>
                                        <span>{words["table.open"]}</span>
                                    </span>
                                {:else}
                                    <OpenHand cards={openCards} />
                                {/if}
                            {:else if !chair.is_mine}
                                <div class="fan-spot">
                                    <BackFan
                                        count={chair.hand.card_count}
                                        dim={chair.is_away || giveUp?.cardsHeld === true}
                                    />
                                </div>
                            {/if}
                            {#if !chair.is_mine && openCards.length === 0}
                                <span class="count-tag" title={words["table.cardCount"]}>
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
            <div class="controls" class:held={giveUp?.cardsHeld === true}>
                {#if ownCards.length > 0}
                    <OwnHand cards={ownCards} {picking} {playing} />
                {/if}
                <div class="actions" class:on-result={onResult}>
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
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                            {`${words["table.weiter"]}`}
                        </button>
                    {:else if bar !== null}
                        <span class="copy wait" role="status">
                            {`${words["table.waitingFor"]} ${bar.names}`}
                            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                        </span>
                    {/if}
                    {#if seated && outcome.table.hand === null}
                        <button type="button" class="copy stand" onclick={() => seat(standUp(id, crypto.randomUUID()))}>
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
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                            <span class="label">{`${words["table.standUp"]}`}</span>
                        </button>
                    {/if}
                    <AgentsPill tableId={id} {streamedVersion} />
                    {#if callMode}
                        <SoundButton place="strip" />
                    {:else}
                        <button type="button" class="copy link" aria-label={words["table.copyLink"]} onclick={copy}>
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
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                            <span class="label">{`${words["table.copyLink"]}`}</span>
                        </button>
                    {/if}
                </div>
                <p class="note" role="status">{note}</p>
            </div>
            {#if agentSat !== null}
                <p class="notice" role="status">
                    <span class="dot agent" aria-hidden="true">
                        <AgentSparkle />
                    </span>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {agentSat} compiles to a `?? ""` branch no sentence can take -->
                    <span class="label">{`${agentSat}`}</span>
                </p>
            {/if}
            {#if taken !== null}
                <p class="notice" role="status">
                    <span class="dot" aria-hidden="true">{taken.slice(0, 1)}</span>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                    <span class="label">{`${words["table.seatTaken"]}`}</span>
                    <b>{taken}</b>
                </p>
            {/if}
        {:else if outcome?.kind === "missing"}
            <TableClosed ended={null} />
        {:else if outcome?.kind === "failed"}
            <section class="panel" role="alert">
                <h1>{words["table.loadFailed"]}</h1>
                <p>{words["table.loadFailedHint"]}</p>
            </section>
        {/if}
    </main>
    <div class="reconnect" role="status" hidden={connected}>
        <span class="spin"></span>{words["table.reconnecting"]}
    </div>
    <footer class="legal">
        <LegalLinks links={LEGAL_LINKS} newTab />
    </footer>
</div>
