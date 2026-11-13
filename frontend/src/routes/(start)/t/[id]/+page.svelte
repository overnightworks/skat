<script lang="ts">
    import { onMount, untrack } from "svelte";
    import { page } from "$app/state";
    import type { PageProps } from "./$types";
    import {
        awayOnTurn,
        chairMarks,
        decidingMarks,
        decidingPlaque,
        PASSED_IN_MARKS,
        passedInScene,
    } from "#lib/auctionMarks.ts";
    import { abortView } from "#lib/abort.ts";
    import { bidLadder } from "#lib/bidLadder.ts";
    import { cuesBetween } from "#lib/cues.ts";
    import { greetCall, isFramedInCallMode } from "#lib/callFrame.ts";
    import { giveUpAsk, giveUpView, refusalNotice } from "#lib/giveUp.ts";
    import { plaqueLine, stampBetween, type Stamp } from "#lib/kontra.ts";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { handWaits, lockedChairs, seatNotice, type SeatNotice } from "#lib/openChair.ts";
    import {
        bidLineOfGameDeclaredInTheStage,
        gameInPlay,
        sideNames,
        trickOnTheFelt,
        type PlayingHand,
    } from "#lib/playView.ts";
    import { ramschMarks, ramschPlaque, ramschTrick } from "#lib/ramschView.ts";
    import {
        declaredResult,
        ramschResultView,
        resultJustAppeared,
        resultView,
        weiterBar,
        withMinus,
    } from "#lib/result.ts";
    import { AiMark, LegalLinks, Marked } from "overnightworks-design";
    import AbortKey from "#lib/ui/AbortKey.svelte";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";
    import AgentsPill from "#lib/ui/AgentsPill.svelte";
    import AnswerMarks from "#lib/ui/AnswerMarks.svelte";
    import AskPlaque from "#lib/ui/AskPlaque.svelte";
    import AwayMark from "#lib/ui/AwayMark.svelte";
    import BackFan from "#lib/ui/BackFan.svelte";
    import CalloutStamp from "#lib/ui/CalloutStamp.svelte";
    import OpenHand from "#lib/ui/OpenHand.svelte";
    import OpenTag from "#lib/ui/OpenTag.svelte";
    import CardBack from "#lib/ui/CardBack.svelte";
    import CardCountTag from "#lib/ui/CardCountTag.svelte";
    import CardSprite from "#lib/ui/CardSprite.svelte";
    import DeclareControls from "#lib/ui/DeclareControls.svelte";
    import BidControls from "#lib/ui/BidControls.svelte";
    import FaceDownSkat from "#lib/ui/FaceDownSkat.svelte";
    import FreeChairTile from "#lib/ui/FreeChairTile.svelte";
    import LockedChairTile from "#lib/ui/LockedChairTile.svelte";
    import GiveUpKey from "#lib/ui/GiveUpKey.svelte";
    import KontraKey from "#lib/ui/KontraKey.svelte";
    import OwnHand from "#lib/ui/OwnHand.svelte";
    import PlayControls from "#lib/ui/PlayControls.svelte";
    import PushControls from "#lib/ui/PushControls.svelte";
    import PlayedTrick from "#lib/ui/PlayedTrick.svelte";
    import PointsBar from "#lib/ui/PointsBar.svelte";
    import RamschMarks from "#lib/ui/RamschMarks.svelte";
    import RamschPlaque from "#lib/ui/RamschPlaque.svelte";
    import RamschResultCard from "#lib/ui/RamschResultCard.svelte";
    import ResultCard from "#lib/ui/ResultCard.svelte";
    import SeatNoticeLine from "#lib/ui/SeatNoticeLine.svelte";
    import SitQuestion from "#lib/ui/SitQuestion.svelte";
    import SoundButton from "#lib/ui/SoundButton.svelte";
    import StandKey from "#lib/ui/StandKey.svelte";
    import TableBar from "#lib/ui/TableBar.svelte";
    import SpeechBubble from "#lib/ui/SpeechBubble.svelte";
    import { bockLine } from "#lib/tableRules.ts";
    import { armSound, soundForCues } from "#lib/tableSound.ts";
    import { words } from "#lib/words.ts";
    import TableClosed from "./TableClosed.svelte";
    import {
        agentSitsNote,
        answerAbort,
        answerGiveUp,
        bidLineWhileDeclaring,
        copyTableLink,
        drawingOrder,
        gameLabel,
        isSuitGame,
        markReady,
        positionWord,
        readTable,
        seatedAgentsKey,
        seriesNumberOf,
        sitDown,
        standUp,
        takeAuctionStep,
        watchTable,
        type AbortAnswer,
        type AuctionAction,
        type Card,
        type GiveUpAnswer,
        type Options,
        type Outcome,
        type Picking,
        type Table,
    } from "../../tables.ts";

    const TAKEN_NOTICE_MILLISECONDS = 4000;
    const WON_MOMENT_MILLISECONDS = 2500;
    const SEAT_NOTICE_MILLISECONDS = 4000;

    const { data }: PageProps = $props();
    // The route has an [id] segment, so the parameter is always present.
    const id = $derived(page.params.id as string);
    let outcome = $state<Outcome | null>(null);
    let note = $state("");
    let taken: string | null = $state(null);
    let connected = $state(true);
    // The number of the person's other tables that wait for him; a lost stream sets it back to none, so a count is never stale.
    let attention = $state(0);
    // The declarer's put-back and the Ramsch's stage each pick two cards; a table has only one of them at a time.
    let declarePicking = $state<Picking | undefined>();
    let pushPicking = $state<Picking | undefined>();
    const picking = $derived(declarePicking ?? pushPicking);
    let playing = $state<PlayingHand | undefined>();
    // The first moment of the declaring, which only a page that sees the auction end shows.
    let justWon = $state(false);
    // The ordinal of the result that appeared while this page watched; only its card counts the gains up.
    let countedOrdinal = $state<number | null>(null);
    // The cards this page saw laid in the running hand; a card that was not seen laid, a reload's for one, is not here.
    let playedThisHand = $state<Card[]>([]);
    // The latest word said at this table in the running hand, which the stamp shows for a moment.
    let stamp = $state<Stamp | null>(null);
    let wonTimer: ReturnType<typeof setTimeout> | undefined;
    // The version of the latest streamed table, which the control that calls agents follows.
    let streamedVersion = $state<number | null>(null);
    // The sentence that names who has just left or taken a chair of the table.
    let seatNote = $state<SeatNotice | null>(null);
    let seatNoteTimer: ReturnType<typeof setTimeout> | undefined;
    // Which agents sit where, so a wake that folds one leaving and another sitting still changes it.
    let seatedAgents = $state("");
    // The free chair whose tap asks the question before a sit, while a hand runs.
    let asking = $state<number | null>(null);

    function showSeatNote(note: SeatNotice): void {
        seatNote = note;
        clearTimeout(seatNoteTimer);
        seatNoteTimer = setTimeout(() => (seatNote = null), SEAT_NOTICE_MILLISECONDS);
    }

    function showTable(previous: Table | undefined, table: Table): void {
        streamedVersion = table.version;
        seatedAgents = seatedAgentsKey(previous, table);
        const note = previous === undefined ? null : (seatNotice(previous, table) ?? agentSitsNote(previous, table));
        if (note !== null) showSeatNote(note);
        if (!handWaits(table.hand)) asking = null;
        if (table.hand?.dealer_seat !== previous?.hand?.dealer_seat) playedThisHand = [];
        stamp = stampBetween(previous, table) ?? stamp;
        const cues = cuesBetween(previous, table);
        soundForCues(cues, table);
        for (const cue of cues) {
            if (cue.kind === "card-played") {
                playedThisHand = [...playedThisHand, cue.card];
            } else if (cue.kind === "give-up-refused") {
                showSeatNote(refusalNotice(table.chairs, cue.seats));
            } else {
                justWon = true;
                clearTimeout(wonTimer);
                wonTimer = setTimeout(() => (justWon = false), WON_MOMENT_MILLISECONDS);
            }
        }
        countedOrdinal = resultJustAppeared(previous, table) ?? (table.result === null ? null : countedOrdinal);
        outcome = { kind: "table", table };
    }

    // SvelteKit keeps this component when the address changes from one table to another.
    $effect(() => {
        outcome = null;
        connected = true;
        attention = 0;
        justWon = false;
        countedOrdinal = null;
        streamedVersion = null;
        seatNote = null;
        asking = null;
        playedThisHand = [];
        stamp = null;
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
                stopWatching = watchTable(
                    id,
                    show,
                    (count) => {
                        attention = count;
                    },
                    (isConnected) => {
                        connected = isConnected;
                        if (!isConnected) {
                            shown = undefined;
                            attention = 0;
                        }
                    },
                );
            }
        });
        // An answer for an address the person has left must not replace the current table.
        return () => {
            current = false;
            clearTimeout(wonTimer);
            clearTimeout(seatNoteTimer);
            stopWatching();
        };
    });

    const seated = $derived(outcome?.kind === "table" && outcome.table.chairs.some((chair) => chair.is_mine));
    const ownTurnLadder = $derived.by(() => {
        if (outcome?.kind !== "table" || outcome.table.hand === null) return null;
        const viewerSeat = outcome.table.chairs.find((chair) => chair.is_mine)?.seat;
        return bidLadder(outcome.table.hand.auction, viewerSeat, handWaits(outcome.table.hand));
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

    // While a hand runs the sit asks first, because the sitter takes over the open chair's cards; a person returns to
    // her own chair without the question.
    function tapFreeChair(chairSeat: number, handRuns: boolean, returning: boolean): void {
        if (handRuns && !returning) asking = chairSeat;
        else void seat(sitDown(id, chairSeat, crypto.randomUUID()));
    }

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

    // A step is under way from the tap until the stream brings a newer version; only a refusal ends it sooner.
    async function send(table: Table, command: Promise<Outcome>): Promise<void> {
        sentFromVersion = table.version;
        if ((await seat(command)).kind !== "table") sentFromVersion = null;
    }

    const tapWeiter = (table: Table): Promise<void> =>
        send(
            table,
            markReady(
                id,
                crypto.randomUUID(),
                (table.result as NonNullable<Table["result"]>).ordinal,
                seriesNumberOf(table),
            ),
        );
    const takeStep = (table: Table, action: AuctionAction, value?: number): Promise<void> =>
        send(table, takeAuctionStep(id, crypto.randomUUID(), table.version, action, value));
</script>

{#snippet cross()}
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
{/snippet}
{#snippet check()}
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
{/snippet}

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    <title>{`${words["app.name"]}`}</title>
</svelte:head>

{#snippet factor({ text }: { text: string })}<b>{text}</b>{/snippet}

{#snippet waitingLine()}
    <span class="gives">
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
        {`${words["table.waitingForPlayers"]}`}
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    </span>
{/snippet}

<div class="room" class:framed={callMode} data-theme="dark">
    <CardSprite />
    {#if !greeted}
        <TableBar
            {callMode}
            {attention}
            {connected}
            live={outcome?.kind === "table" && outcome.table.ended === null
                ? {
                      watchers: outcome.table.watchers,
                      options: outcome.table.options as Options,
                      bock: outcome.table.bock,
                  }
                : null}
        />
    {/if}
    <main class="stage" class:stale={!connected} class:after-drop={greeted}>
        {#if outcome?.kind === "table" && outcome.table.ended !== null}
            <TableClosed ended={outcome.table.ended} />
        {:else if outcome?.kind === "table"}
            {@const ownCards = outcome.table.hand?.own_cards ?? []}
            <!-- A chair waits only on a seated viewer, and a seated viewer's chair always carries their name. -->
            {@const ownChair = outcome.table.chairs.find((chair) => chair.is_mine)}
            {@const ownInitial = String(ownChair?.occupant_name).slice(0, 1)}
            {@const bidLine = bidLineWhileDeclaring(outcome.table)}
            {@const inPlay = gameInPlay(outcome.table)}
            {@const ramschTable = outcome.table}
            {@const ramsch = ramschPlaque(outcome.table)}
            {@const trick = inPlay?.playing ?? ramschTrick(outcome.table)}
            {@const waits = handWaits(outcome.table.hand)}
            {@const locked = lockedChairs(outcome.table)}
            {@const turnSeat = waits ? undefined : inPlay?.playing.turn_seat}
            {@const declared = declaredResult(outcome.table)}
            {@const view = declared === null ? null : resultView(outcome.table)}
            {@const ramschView = ramschResultView(outcome.table)}
            {@const onResult = view !== null || ramschView !== null}
            {@const winners = new Set((view ?? ramschView)?.rows.filter((row) => row.won).map((row) => row.seat))}
            {@const bar = weiterBar(outcome.table)}
            {@const passedIn = passedInScene(outcome.table.passed_in, outcome.table.chairs)}
            {@const deciding = decidingPlaque(outcome.table, justWon)}
            {@const giveUp = giveUpView(outcome.table)}
            {@const abort = abortView(outcome.table)}
            {#if onResult}
                <!-- The card carries the game and the points, so the plaque stays out while a result stands. -->
            {:else if abort.ask !== null}
                {@const table = outcome.table}
                <AskPlaque
                    view={abort.ask}
                    disabled={sentFromVersion === table.version}
                    onanswer={(answer: AbortAnswer) => {
                        void send(table, answerAbort(id, crypto.randomUUID(), answer));
                    }}
                />
            {:else if deciding !== null}
                <div class="plaque deciding">
                    {#if deciding.kind === "won"}
                        <span>{deciding.text}</span>
                    {:else}
                        <span>{deciding.bid}</span>
                        <span class="gives">
                            {deciding.line}
                            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                        </span>
                    {/if}
                </div>
            {:else if bidLine !== null}
                <div class="plaque">
                    <span>{bidLine}</span>
                </div>
            {:else if ramsch !== null}
                <RamschPlaque plaque={ramsch} />
            {:else if inPlay !== null}
                {@const label = gameLabel(inPlay.declaration)}
                {@const running = inPlay.playing.running_points}
                {@const said = plaqueLine(inPlay.playing.kontra)}
                {@const stageBid = bidLineOfGameDeclaredInTheStage(outcome.table)}
                {#if giveUp !== null}
                    {@const table = outcome.table}
                    <AskPlaque
                        view={giveUpAsk(giveUp)}
                        disabled={sentFromVersion === table.version}
                        onanswer={(answer: GiveUpAnswer) => {
                            void send(table, answerGiveUp(id, table.version, crypto.randomUUID(), answer));
                        }}
                    >
                        {#if running !== null}
                            <PointsBar sides={sideNames(table.chairs, inPlay.declarerSeat)} points={running} />
                        {/if}
                    </AskPlaque>
                {:else}
                    {@const bock = bockLine(outcome.table.bock)}
                    <div
                        class="plaque"
                        class:wide={label.announcement !== null}
                        class:counting={running !== null}
                        class:deciding={waits}
                    >
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
                        {#if stageBid !== null}
                            <span class="game pushes">{stageBid}</span>
                        {/if}
                        {#if said !== null}
                            <span class="game pushes"><Marked parts={said} marked={{ factor }} /></span>
                        {/if}
                        {#if waits}
                            {@render waitingLine()}
                        {/if}
                        {#if bock !== null}
                            <div class="bock-line"><Marked parts={bock} marked={{ factor }} /></div>
                        {/if}
                        {#if running !== null}
                            <PointsBar sides={sideNames(outcome.table.chairs, inPlay.declarerSeat)} points={running} />
                        {/if}
                    </div>
                {/if}
            {:else if !outcome.table.hand?.declaring}
                {@const awayName = outcome.table.hand && awayOnTurn(outcome.table.hand.auction, outcome.table.chairs)}
                <div
                    class="plaque"
                    class:hand-over={passedIn !== null}
                    class:deciding={waits || outcome.table.aborted !== null}
                >
                    {#if passedIn !== null}
                        <span class="verdict">{words["table.passedIn"]}</span>
                        {#if passedIn.dealerLine !== null}
                            <span class="gives">
                                {passedIn.dealerLine}
                                <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                            </span>
                        {/if}
                    {:else if outcome.table.aborted !== null}
                        <span>{words["table.aborted"]}</span>
                        {@render waitingLine()}
                    {:else if outcome.table.hand === null}
                        <span>{words["table.waitingForPlayers"]}</span>
                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                    {:else if awayName && !waits}
                        <span>{words["table.waitingFor"]({ names: awayName })}</span>
                        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                    {:else}
                        <span>{words["table.bidding"]}</span>
                        {#if waits}
                            {@render waitingLine()}
                        {/if}
                    {/if}
                </div>
            {/if}
            <div class="felt" aria-hidden="true"></div>
            {#if view !== null}
                <ResultCard {view} counts={declared?.ordinal === countedOrdinal} />
            {:else if ramschView !== null}
                <RamschResultCard view={ramschView} />
            {/if}
            {@const nearCardLaid =
                trick !== null && trickOnTheFelt(outcome.table.chairs, trick).some(({ slot }) => slot === "near")}
            <CalloutStamp {stamp} aboveNearCard={nearCardLaid} />
            {#if trick !== null}
                <PlayedTrick chairs={outcome.table.chairs} playing={trick} {playedThisHand} />
            {/if}
            {@const dealerSeat = passedIn?.dealerSeat ?? outcome.table.hand?.dealer_seat}
            {@const auction = outcome.table.hand?.auction}
            {@const declaring = outcome.table.hand?.declaring}
            {#if outcome.table.hand !== null && trick === null}
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
                              ? decidingMarks(declaring, chair.seat, justWon, waits)
                              : chairMarks(auction, chair.seat, ownChair?.seat, waits)}
                    {@const ramschMark = ramschMarks(ramschTable, chair.seat)}
                    {@const onTurn = marks.turn || chair.seat === turnSeat || ramschMark.turn}
                    {@const openCards = chair.seat === declaring?.declarer_seat ? declaring.open_cards : []}
                    <li
                        class="chair"
                        class:mine={chair.is_mine}
                        class:away={chair.is_away}
                        class:out={marks.passed}
                        class:win={winners.has(chair.seat)}
                        class:turn={onTurn}
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
                                <AnswerMarks mark={(giveUp?.marks ?? abort.marks).get(chair.seat)} />
                                {#if onTurn}
                                    <span class="mark turn" aria-hidden="true">
                                        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                            <path d="M8 5l11 7-11 7z" />
                                        </svg>
                                    </span>
                                {:else if marks.passed}
                                    <span class="mark pass">
                                        {@render cross()}
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
                                <RamschMarks marks={ramschMark} initial={chair.occupant_name.slice(0, 1)} />
                            {/if}
                            {#if onResult}
                                <AnswerMarks mark={chair.ready ? "ready" : "unready"} />
                            {/if}
                            {#if chair.is_away}
                                <AwayMark />
                            {/if}
                        {:else if seated}
                            <span class="tile empty"></span>
                        {:else if locked.has(chair.seat)}
                            <LockedChairTile />
                        {:else}
                            <FreeChairTile
                                ontap={() => {
                                    tapFreeChair(chair.seat, waits, chair.is_mine_to_return);
                                }}
                            />
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
                                    <OpenTag />
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
                                <CardCountTag count={chair.hand.card_count} />
                            {/if}
                        {/if}
                    </li>
                {/each}
            </ul>
            <DeclareControls {id} table={outcome.table} bind:picking={declarePicking} bind:note />
            <PushControls {id} table={outcome.table} bind:picking={pushPicking} bind:note />
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
                    <KontraKey {id} table={outcome.table} bind:note />
                    <AbortKey {id} table={outcome.table} bind:note />
                    {#if bar?.kind === "tap"}
                        {@const table = outcome.table}
                        <button
                            type="button"
                            class="copy weiter"
                            disabled={sentFromVersion === table.version && !bar.again}
                            onclick={() => tapWeiter(table)}
                        >
                            {@render check()}
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                            {`${words["table.weiter"]}`}
                        </button>
                    {:else if bar !== null}
                        <span class="copy wait" role="status">
                            {bar.text}
                            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                        </span>
                    {/if}
                    <GiveUpKey {id} table={outcome.table} bind:note />
                    {#if seated}
                        <StandKey
                            handRuns={outcome.table.hand !== null}
                            onstand={() => {
                                void seat(standUp(id, crypto.randomUUID()));
                            }}
                        />
                    {/if}
                    <AgentsPill tableId={id} {streamedVersion} {seatedAgents} kitWords={data.kitWords} />
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
            {#if seatNote !== null}
                <SeatNoticeLine notice={seatNote} />
            {/if}
            {@const asked = waits
                ? outcome.table.chairs.find((chair) => chair.seat === asking && chair.occupant_name === null)
                : undefined}
            {#if asked !== undefined}
                <SitQuestion
                    formerHolder={asked.former_holder_name}
                    onsit={() => {
                        void seat(sitDown(id, asked.seat, crypto.randomUUID()));
                        asking = null;
                    }}
                    oncancel={() => {
                        asking = null;
                    }}
                />
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
        <LegalLinks links={LEGAL_LINKS} newTab words={data.kitWords} />
    </footer>
</div>
