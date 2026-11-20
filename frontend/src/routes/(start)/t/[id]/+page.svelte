<script lang="ts">
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { resolve } from "$app/paths";
    import { page } from "$app/state";
    import type { PageProps } from "./$types";
    import { chairMarks, decidingMarks, decidingPlaque, PASSED_IN_MARKS, passedInScene } from "#lib/auctionMarks.ts";
    import { abortView } from "#lib/abort.ts";
    import { grumblingAt, ring, stopRinging } from "#lib/bell.svelte.ts";
    import { bidLadder } from "#lib/bidLadder.ts";
    import { tableShowing, type DecidingTrick, type Presenter } from "#lib/closingHand.ts";
    import { springsUp, stampBetween, type BidWord } from "#lib/cues.ts";
    import { isFramedInCallMode } from "#lib/callFrame.ts";
    import {
        answerGiveUp,
        giveUpAsk,
        giveUpView,
        openCardsMark,
        requestEndedNotice,
        type GiveUpAnswer,
    } from "#lib/giveUp.ts";
    import { firstCardWait, keyWord, type Stamp } from "#lib/kontra.ts";
    import { handWaits, lockedChairs, noticeStanding, seatNotice, type SeatNotice } from "#lib/openChair.ts";
    import {
        bidLineOfGameDeclaredInTheStage,
        gameInPlay,
        openCardsOf,
        sideNames,
        type PlayingHand,
    } from "#lib/playView.ts";
    import { ramschMarks, ramschPlaque, ramschTrick } from "#lib/ramschView.ts";
    import {
        nextSettingsRevisionOf,
        resultOnStage,
        returnsToLobby,
        seriesCountText,
        seriesEndView,
        seriesOver,
        standingsView,
        stopOffered,
    } from "#lib/series.ts";
    import { declaredResult, ramschResultView, resultView, weiterBar, withMinus } from "#lib/result.ts";
    import { AiMark, Marked } from "overnightworks-design";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";
    import AnswerMarks from "#lib/ui/AnswerMarks.svelte";
    import AskPlaque from "#lib/ui/AskPlaque.svelte";
    import AwayMark from "#lib/ui/AwayMark.svelte";
    import BackFan from "#lib/ui/BackFan.svelte";
    import CallSeats from "#lib/ui/CallSeats.svelte";
    import DecidingPlaque from "#lib/ui/DecidingPlaque.svelte";
    import OpenHand from "#lib/ui/OpenHand.svelte";
    import OpenTag from "#lib/ui/OpenTag.svelte";
    import DealerMark from "#lib/ui/DealerMark.svelte";
    import DeclarerMark from "#lib/ui/DeclarerMark.svelte";
    import CardCountTag from "#lib/ui/CardCountTag.svelte";
    import CardDeck from "#lib/ui/CardDeck.svelte";
    import CardSprite from "#lib/ui/CardSprite.svelte";
    import DeclareControls from "#lib/ui/DeclareControls.svelte";
    import BidControls from "#lib/ui/BidControls.svelte";
    import FaceDownSkat from "#lib/ui/FaceDownSkat.svelte";
    import FreeChairTile from "#lib/ui/FreeChairTile.svelte";
    import LockedChairTile from "#lib/ui/LockedChairTile.svelte";
    import KontraKey from "#lib/ui/KontraKey.svelte";
    import KontraLines from "#lib/ui/KontraLines.svelte";
    import NudgeBell from "#lib/ui/NudgeBell.svelte";
    import OwnHand from "#lib/ui/OwnHand.svelte";
    import PassMark from "#lib/ui/PassMark.svelte";
    import PlayControls from "#lib/ui/PlayControls.svelte";
    import PushControls from "#lib/ui/PushControls.svelte";
    import PointsBar from "#lib/ui/PointsBar.svelte";
    import RamschMarks from "#lib/ui/RamschMarks.svelte";
    import RamschPlaque from "#lib/ui/RamschPlaque.svelte";
    import RamschResultCard from "#lib/ui/RamschResultCard.svelte";
    import ResultCard from "#lib/ui/ResultCard.svelte";
    import SeatNoticeLine from "#lib/ui/SeatNoticeLine.svelte";
    import SeriesEnd from "#lib/ui/SeriesEnd.svelte";
    import SitQuestion from "#lib/ui/SitQuestion.svelte";
    import TakenNotice from "#lib/ui/TakenNotice.svelte";
    import SoundButton from "#lib/ui/SoundButton.svelte";
    import KlassikDecor from "#lib/ui/KlassikDecor.svelte";
    import StrandDecor from "#lib/ui/StrandDecor.svelte";
    import ThrownEmotes from "#lib/ui/ThrownEmotes.svelte";
    import StyleScene from "#lib/ui/StyleScene.svelte";
    import TrickPile from "#lib/ui/TrickPile.svelte";
    import WaitingLine from "#lib/ui/WaitingLine.svelte";
    import WaitingPlaque from "#lib/ui/WaitingPlaque.svelte";
    import TrickStage from "#lib/ui/TrickStage.svelte";
    import TableBar from "#lib/ui/TableBar.svelte";
    import MenuKey from "#lib/ui/MenuKey.svelte";
    import TableMenu from "#lib/ui/TableMenu.svelte";
    import WeiterKey from "#lib/ui/WeiterKey.svelte";
    import SpeechBubble from "#lib/ui/SpeechBubble.svelte";
    import { bockLine } from "#lib/tableRules.ts";
    import { motionInForce } from "#lib/settings.svelte.ts";
    import {
        chairMoving,
        isDealing,
        receiveOnStage,
        resetStage,
        stageMoves,
        sweepingTo,
        trickIsMoving,
    } from "#lib/stage.svelte.ts";
    import { beatOf, receiveReactions, resetReactions } from "#lib/tableReactions.svelte.ts";
    import { armSound, soundForCues } from "#lib/tableSound.ts";
    import { tableStyle } from "#lib/tableStyle.svelte.ts";
    import { words } from "#lib/words.ts";
    import TableClosed from "./TableClosed.svelte";
    import {
        answerAbort,
        answerSeriesEnd,
        bidLineWhileDeclaring,
        copyTableLink,
        drawingOrder,
        gameLabel,
        isSuitGame,
        positionWord,
        readGameSheet,
        readTable,
        seatedAgentsKey,
        sitDown,
        standUp,
        stopPlaying,
        takeAuctionStep,
        watchTable,
        type AbortAnswer,
        type SeriesEndAnswer,
        type AuctionAction,
        type Card,
        type Options,
        type Outcome,
        type Picking,
        type Table,
    } from "../../tables.ts";
    import { nudgedNote } from "../../nudge.ts";
    import { markReady, seriesNumberOf, startNewSeries } from "../../seriesCommands.ts";
    import { reactionName, reactionsBetween, throwReaction } from "../../reaction.ts";

    const TAKEN_NOTICE_MILLISECONDS = 4000;
    const WON_MOMENT_MILLISECONDS = 2500;
    const SEAT_NOTICE_MILLISECONDS = 4000;

    const { data }: PageProps = $props();
    // The route has an [id] segment, so the parameter is always present.
    const id = $derived(page.params.id as string);
    let outcome = $state<Outcome | null>(null);
    let note = $state("");
    let rulesOpen = $state(false);
    let taken: string | null = $state(null);
    let connected = $state(true);
    let streamsFull = $state(false);
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
    // The trick that decided a game before its tenth, shown on its result as the stage stood still.
    let stillTrick = $state<DecidingTrick | null>(null);
    // The cards this page saw laid in the running hand; a card that was not seen laid, a reload's for one, is not here.
    let playedThisHand = $state<Card[]>([]);
    // The latest word said at this table in the running hand, which the stamp shows for a moment.
    let stamp = $state<Stamp | null>(null);
    // The latest bid this page saw said, whose bubble springs up.
    let bidSaid = $state<{ seat: number; word: BidWord } | null>(null);
    let wonTimer: ReturnType<typeof setTimeout> | undefined;
    // The version of the latest streamed table, which the control that calls agents follows.
    let streamedVersion = $state<number | null>(null);
    // How many people watch without a chair, which the agents list follows while it is open.
    let streamedWatchers = $state(0);
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

    const presentTable: Presenter = (previous, table, cues, closing) => {
        streamedVersion = table.version;
        streamedWatchers = table.watchers;
        seatedAgents = seatedAgentsKey(previous, table);
        const nudged = previous === undefined ? null : nudgedNote(previous, table);
        const note = requestEndedNotice(cues, table.chairs) ?? seatNotice(cues, table) ?? nudged;
        if (note !== null) showSeatNote(note);
        seatNote = noticeStanding(seatNote, table);
        if (!handWaits(table.hand)) asking = null;
        if (previous === undefined || cues.some((cue) => cue.kind === "dealt")) playedThisHand = [];
        stamp = stampBetween(previous, table) ?? stamp;
        soundForCues(cues, table);
        receiveReactions(reactionsBetween(previous, table));
        for (const cue of cues) {
            if (cue.kind === "card-played") {
                playedThisHand = [...playedThisHand, cue.card];
            } else if (cue.kind === "bid-said") {
                bidSaid = cue;
            } else if (cue.kind === "nudged") {
                ring(cue);
            } else if (cue.kind === "result-appeared") {
                countedOrdinal = cue.ordinal;
            } else if (cue.kind === "auction-ended") {
                justWon = true;
                clearTimeout(wonTimer);
                wonTimer = setTimeout(() => (justWon = false), WON_MOMENT_MILLISECONDS);
            }
        }
        if (table.result === null) countedOrdinal = null;
        outcome = { kind: "table", table };
        if (returnsToLobby(previous, table)) void goto(resolve("/(start)"));
        // The stage may show the result at once, so nothing of this table is set after it.
        receiveOnStage(previous, cues, closing);
    };

    const tables = tableShowing(
        presentTable,
        (ordinal) => readGameSheet(id, ordinal),
        stageMoves,
        (deciding) => (stillTrick = deciding),
    );

    // SvelteKit keeps this component when the address changes from one table to another.
    $effect(() => {
        outcome = null;
        connected = true;
        streamsFull = false;
        attention = 0;
        justWon = false;
        countedOrdinal = null;
        stillTrick = null;
        streamedVersion = null;
        seatNote = null;
        asking = null;
        playedThisHand = [];
        stamp = null;
        bidSaid = null;
        resetStage();
        stopRinging();
        resetReactions();
        let current = true;
        let stopWatching = (): void => {};
        void readTable(id).then((answer) => {
            if (!current) return;
            outcome = answer;
            if (answer.kind === "table" && answer.table.ended === null) {
                tables.begin(answer.table);
                stopWatching = watchTable(
                    id,
                    tables.show,
                    (count) => {
                        attention = count;
                    },
                    (isConnected) => {
                        connected = isConnected;
                        if (isConnected) streamsFull = false;
                        else {
                            tables.forget();
                            attention = 0;
                        }
                    },
                    (refusal) => {
                        if (refusal === "tooMany") {
                            streamsFull = true;
                            return;
                        }
                        // No table has the id any more, and nothing reconnects to one.
                        outcome = { kind: "missing" };
                        connected = true;
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
            tables.end();
            resetStage();
            stopRinging();
            resetReactions();
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

    // After the series' last game the same tap is „Neue Serie“, which names the series it saw as „Weiter“ does.
    const tapWeiter = (table: Table): Promise<void> =>
        send(
            table,
            seriesOver(table)
                ? startNewSeries(id, crypto.randomUUID(), seriesNumberOf(table), nextSettingsRevisionOf(table))
                : markReady(
                      id,
                      crypto.randomUUID(),
                      (table.result as NonNullable<Table["result"]>).ordinal,
                      seriesNumberOf(table),
                  ),
        );
    const takeStep = (table: Table, action: AuctionAction, value?: number): Promise<void> =>
        send(table, takeAuctionStep(id, crypto.randomUUID(), table.version, action, value));
</script>

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    <title>{`${words["app.name"]}`}</title>
</svelte:head>

{#snippet factor({ text }: { text: string })}<b>{text}</b>{/snippet}

{#snippet tableMenu(place: "bar" | "strip")}
    {#if outcome?.kind === "table" && outcome.table.ended === null}
        {@const table = outcome.table}
        <TableMenu
            {id}
            {table}
            bind:note
            {place}
            {callMode}
            {seated}
            styleOffered={seated && !resultOnStage(table) && keyWord(table) === null}
            oncopy={copy}
            onrules={() => {
                rulesOpen = true;
            }}
            onstand={() => {
                void seat(standUp(id, crypto.randomUUID()));
            }}
            {streamedVersion}
            {seatedAgents}
            watchers={streamedWatchers}
            kitWords={data.kitWords}
        />
    {:else if outcome !== null}
        <MenuKey {place} kitWords={data.kitWords} />
    {/if}
{/snippet}

<div
    class="room"
    class:framed={callMode}
    class:dealing={isDealing()}
    data-theme="dark"
    data-motion={motionInForce()}
    data-style={tableStyle()}
>
    <div class="room-paint" aria-hidden="true" data-call-backdrop></div>
    {#if callMode}
        <CallSeats
            tableId={id}
            table={outcome?.kind === "table" ? outcome.table : null}
            missing={outcome?.kind === "missing"}
            ongreeted={() => {
                greeted = true;
            }}
        />
    {/if}
    <StyleScene style={outcome?.kind === "table" ? outcome.table.style : null} />
    <CardSprite />
    {#if !greeted}
        <TableBar
            {callMode}
            {attention}
            {connected}
            bind:rulesOpen
            live={outcome?.kind === "table" && outcome.table.ended === null
                ? {
                      id,
                      version: outcome.table.version,
                      watchers: outcome.table.watchers,
                      options: outcome.table.options as Options,
                      bock: outcome.table.bock,
                      count: seriesCountText(outcome.table),
                  }
                : null}
        >
            {#snippet menu()}
                {@render tableMenu("bar")}
            {/snippet}
        </TableBar>
    {/if}
    <main class="stage" class:stale={!connected} class:after-drop={greeted}>
        {#if outcome?.kind === "table" && outcome.table.ended !== null}
            <TableClosed ended={outcome.table.ended} />
        {:else if outcome?.kind === "table"}
            {@const ownCards = outcome.table.hand?.own_cards ?? []}
            {@const declaredGame = outcome.table.hand?.declaring?.declaration?.game ?? null}
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
            {@const wait = firstCardWait(outcome.table)}
            {@const turnSeat = waits || wait || trickIsMoving() ? undefined : inPlay?.playing.turn_seat}
            {@const seriesEnd = seriesEndView(outcome.table)}
            {@const declared = declaredResult(outcome.table)}
            {@const view = declared === null || seriesEnd.onStage ? null : resultView(outcome.table)}
            {@const ramschView = seriesEnd.onStage ? null : ramschResultView(outcome.table)}
            {@const standing = standingsView(outcome.table)}
            {@const onResult = resultOnStage(outcome.table)}
            {@const winners =
                standing?.winnerSeats ??
                new Set((view ?? ramschView)?.rows.filter((row) => row.won).map((row) => row.seat))}
            {@const current = outcome.table}
            {@const bar = weiterBar(outcome.table)}
            {@const passedIn = standing === null ? passedInScene(outcome.table.passed_in, outcome.table.chairs) : null}
            {@const deciding = decidingPlaque(outcome.table, justWon)}
            {@const giveUp = giveUpView(outcome.table)}
            {@const abort = abortView(outcome.table)}
            {#if seriesEnd.ask !== null}
                {@const table = outcome.table}
                <AskPlaque
                    view={seriesEnd.ask}
                    disabled={sentFromVersion === table.version}
                    onanswer={(answer: SeriesEndAnswer) => {
                        void send(table, answerSeriesEnd(id, crypto.randomUUID(), answer));
                    }}
                />
            {:else if onResult}
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
                <DecidingPlaque {deciding} />
            {:else if bidLine !== null}
                <div class="plaque">
                    <span>{bidLine}</span>
                </div>
            {:else if ramsch !== null}
                <RamschPlaque plaque={ramsch} />
            {:else if inPlay !== null}
                {@const label = gameLabel(inPlay.declaration)}
                {@const running = inPlay.playing.running_points}
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
                        class:deciding={waits || wait !== null}
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
                        <KontraLines kontra={inPlay.playing.kontra} {wait} />
                        {#if waits}
                            <WaitingLine />
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
                <WaitingPlaque table={outcome.table} {passedIn} {waits} />
            {/if}
            <div class="felt-paint" aria-hidden="true" data-call-backdrop></div>
            <div class="felt">
                <StrandDecor {id} />
                <KlassikDecor {id} />
                <ThrownEmotes chairs={outcome.table.chairs} />
            </div>
            {#if standing !== null}
                <SeriesEnd {id} table={outcome.table} view={standing} {seat} />
            {:else if view !== null}
                <ResultCard
                    {view}
                    counts={declared?.ordinal === countedOrdinal}
                    deciding={stillTrick?.ordinal === declared?.ordinal ? stillTrick : null}
                />
            {:else if ramschView !== null}
                <RamschResultCard view={ramschView} />
            {/if}
            <TrickStage chairs={outcome.table.chairs} playing={trick} {playedThisHand} {turnSeat} {stamp} />
            {@const dealerSeat = passedIn?.dealerSeat ?? outcome.table.hand?.dealer_seat}
            {@const auction = outcome.table.hand?.auction}
            {@const declaring = outcome.table.hand?.declaring}
            {#if outcome.table.hand !== null && trick === null}
                <div class="skat-spot">
                    <FaceDownSkat count={outcome.table.hand.skat_count} />
                </div>
            {:else if passedIn !== null}
                <div class="skat-spot">
                    <CardDeck />
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
                    {@const onTurn = marks.turn || chair.seat === turnSeat || ramschMark.turn || wait?.owes(chair.seat)}
                    {@const openCards = openCardsOf(current, chair.seat)}
                    {@const held = giveUp?.cardsHeld === true || wait?.held(chair.seat)}
                    <li
                        class="chair"
                        class:mine={chair.is_mine}
                        class:away={chair.is_away}
                        class:out={marks.passed}
                        class:win={winners.has(chair.seat)}
                        class:got={chair.seat === sweepingTo()}
                        class:turn={onTurn}
                        class:nudgeable={chair.nudge !== null}
                        class:shaken={grumblingAt(chair.seat) !== null}
                        data-seat={chair.seat}
                        data-moving={chairMoving(chair.seat)}
                    >
                        {#if chair.is_mine}
                            <span class="bar-pill" aria-hidden="true" data-call-backdrop></span>
                        {/if}
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
                            <span class="mark-row">
                                {#if chair.hand !== null || passedIn !== null || onResult}
                                    {#if chair.seat === dealerSeat}
                                        <DealerMark />
                                    {/if}
                                    {#if chair.hand !== null}
                                        <span class="mark pos">{positionWord(chair.hand.position)}</span>
                                    {/if}
                                    {#if marks.declarer || chair.seat === (declared?.declarer_seat ?? inPlay?.declarerSeat)}
                                        <DeclarerMark won={marks.declarer === "won"} />
                                    {/if}
                                    <AnswerMarks
                                        mark={(giveUp?.marks ?? abort.marks).get(chair.seat) ??
                                            seriesEnd.marks.get(chair.seat) ??
                                            openCardsMark(current, chair.seat)}
                                    />
                                    <AnswerMarks mark={wait?.marks.get(chair.seat)} />
                                    {#if onTurn}
                                        <span class="mark turn" aria-hidden="true">
                                            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                                <path d="M8 5l11 7-11 7z" />
                                            </svg>
                                        </span>
                                    {:else if marks.passed}
                                        <PassMark />
                                    {:else if marks.waits}
                                        <span class="mark waits" title={words["table.waitsForYou"]}>
                                            <span class="dot" aria-hidden="true">{ownInitial}</span>
                                            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
                                        </span>
                                    {/if}
                                    <SpeechBubble
                                        bubble={grumblingAt(chair.seat) === null ? marks.bubble : null}
                                        initial={chair.occupant_name.slice(0, 1)}
                                        fresh={springsUp(bidSaid, chair.seat, marks.bubble)}
                                    />
                                    <RamschMarks marks={ramschMark} initial={chair.occupant_name.slice(0, 1)} />
                                    <NudgeBell
                                        {id}
                                        version={current.version}
                                        seat={chair.seat}
                                        name={chair.occupant_name}
                                        nudge={chair.nudge}
                                        grumble={grumblingAt(chair.seat)}
                                    />
                                {/if}
                                {#if onResult && !seriesEnd.onStage}
                                    <AnswerMarks mark={chair.ready ? "ready" : "unready"} />
                                {/if}
                                {#if chair.is_away}
                                    <AwayMark />
                                {/if}
                            </span>
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
                        <TrickPile seat={chair.seat} playing={trick} />
                        <span class="plate"
                            >{chair.is_mine
                                ? words["table.sideYou"]
                                : (chair.occupant_name ??
                                  words["table.seatFree"])}{#if chair.occupant_kind === "agent"}<AiMark
                                />{/if}{#if chair.is_away}<small class="away-note">{words["table.seatAway"]}</small
                                >{/if}</span
                        >
                        {#if chair.total !== null}
                            <button
                                type="button"
                                class="coaster"
                                data-beat={beatOf("coaster")}
                                aria-label={`${words[reactionName("coaster")]} ${withMinus(chair.total)}`}
                                onclick={() => {
                                    void throwReaction(id, "coaster");
                                }}
                            >
                                {withMinus(chair.total)}
                            </button>
                        {/if}
                        {#if chair.hand !== null}
                            {#if openCards.length > 0}
                                {#if chair.is_mine}
                                    <OpenTag />
                                {:else}
                                    <OpenHand cards={openCards} game={declaredGame} dim={held} />
                                {/if}
                            {:else if !chair.is_mine}
                                <div class="fan-spot">
                                    <BackFan count={chair.hand.card_count} dim={chair.is_away || held} />
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
            <div class="controls" class:held={giveUp?.cardsHeld === true || wait?.held(ownChair?.seat)}>
                {#if ownCards.length > 0}
                    <OwnHand cards={ownCards} game={declaredGame} {picking} {playing} />
                {/if}
                <div class="actions" class:on-result={onResult}>
                    <KontraKey {id} table={outcome.table} bind:note />
                    <WeiterKey
                        {bar}
                        watching={standing !== null}
                        newSeries={seriesOver(current)}
                        sent={sentFromVersion === current.version}
                        ontap={() => tapWeiter(current)}
                        onstop={stopOffered(current)
                            ? () => send(current, stopPlaying(id, crypto.randomUUID()))
                            : undefined}
                    />
                    {#if callMode && standing === null}
                        <SoundButton place="strip" />
                        {@render tableMenu("strip")}
                    {/if}
                </div>
                <p class="note" role="status">{note}</p>
            </div>
            {#if seatNote !== null}
                <SeatNoticeLine notice={seatNote} />
            {:else if seriesEnd.refusal !== null}
                <SeatNoticeLine notice={seriesEnd.refusal} below />
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
                <TakenNotice name={taken} />
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
        <span class="spin"></span>{streamsFull ? words["table.tooManyStreams"] : words["table.reconnecting"]}
    </div>
</div>
