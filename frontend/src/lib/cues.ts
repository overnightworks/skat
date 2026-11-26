import type { Bubble } from "./auctionMarks.ts";
import { stampOf, type SaidWord, type Stamp } from "./kontra.ts";
import { handWaits } from "./openChair.ts";
import { declaredResult, resultIsGood } from "./result.ts";
import {
    type AuctionAction,
    type Card,
    type Chair,
    type ChairHand,
    type Declaring,
    type LastTrick,
    type Playing,
    type SeatedCard,
    type Table,
} from "../routes/(start)/tables.ts";
import { seatsInTurnFrom } from "./turnOrder.ts";
import { nudgedChairs } from "../routes/(start)/nudge.ts";

const SEATS_AT_A_TABLE = 3;

// What a chair said in the auction that the table shows: a bid or a hold with its value, or a pass.
export type BidWord = { action: Exclude<AuctionAction, "play">; value: number | null };
export type BidSaid = { seat: number; word: BidWord };

// Who a chair changed hands with: the one who sat down or the one who left, and whether she is the viewer.
type Sitter = { seat: number; name: string; agent: boolean; mine: boolean };

// A chair that was open and now holds someone; `inHand` when it was an open chair of the running hand, whose cards the
// sitter takes over.
export type TakenCue = { kind: "chair-taken"; inHand: boolean } & Sitter;
// A chair that was held between hands and is open now.
export type StoodCue = { kind: "chair-stood" } & Sitter;
// A chair of the running hand that is open now, which the hand waits on.
export type OpenedCue = { kind: "chair-opened" } & Sitter;
export type ChairCue = TakenCue | StoodCue | OpenedCue;

export type Cue =
    | ChairCue
    | { kind: "card-played"; seat: number; card: Card }
    | { kind: "auction-ended" }
    // The trick this update's completing card finished, which goes to its taker.
    | { kind: "trick-taken"; trick: LastTrick }
    // The seats of the opponents who both said no to the declarer's give-up.
    | { kind: "give-up-refused"; seats: number[] }
    // The opponent whose no ended the declarer's shortening; the game goes on with the declarer's cards open.
    | { kind: "shortening-refused"; seat: number }
    // The declarer played on against an opponent's wrong open play; that opponent's cards lie open.
    | { kind: "open-play-on"; seat: number }
    | ({ kind: "bid-said" } & BidSaid)
    | { kind: "word-said"; said: SaidWord }
    // The game the declarer declared, with what the table's announcement shows of it.
    | ({ kind: "game-announced" } & NonNullable<Declaring["declaration"]>)
    // The viewer is on turn in a phase of the hand where another chair, or no chair, was before.
    | { kind: "turn-came" }
    // A hand was dealt to a table that was waiting for one.
    | { kind: "dealt" }
    // A chair the table waits for was nudged. Every page of the table computes the same `pick` from the nudge, which
    // picks the line the chair grumbles.
    | { kind: "nudged"; seat: number; pick: number }
    // The declared result the update brought: whether it is good news for the viewer, and whether a seat's gain counts up.
    | { kind: "result-appeared"; ordinal: number; won: boolean; counts: boolean };

// The one owner of what just happened between two versions of a table. A table that is not newer than the one
// before it yields nothing, and so does a change the two versions do not fully explain.
export function cuesBetween(previous: Table | undefined, next: Table): Cue[] {
    if (previous === undefined || next.version < previous.version) return [];
    const nudges = nudgedCuesBetween(previous, next);
    // A nudge moves no version, so it is the one cue a table of the same version can bring.
    if (next.version === previous.version) return nudges;
    const cues: Cue[] = chairCuesBetween(previous, next);
    if (auctionJustEnded(previous, next)) cues.push({ kind: "auction-ended" });
    cues.push(...cardCuesBetween(previous, next));
    const refusers = giveUpRefusedBetween(previous, next);
    if (refusers !== null) cues.push({ kind: "give-up-refused", seats: refusers });
    const shorteningRefuser = shorteningRefusedBetween(previous, next);
    if (shorteningRefuser !== null) cues.push({ kind: "shortening-refused", seat: shorteningRefuser });
    const openPlayer = openPlayPlayedOnBetween(previous, next);
    if (openPlayer !== null) cues.push({ kind: "open-play-on", seat: openPlayer });
    for (const bid of bidsSaidBetween(previous, next)) cues.push({ kind: "bid-said", ...bid });
    const declared = next.hand?.declaring?.declaration ?? null;
    if (declared !== null && !sameJson(previous.hand?.declaring?.declaration, declared))
        cues.push({ kind: "game-announced", ...declared });
    const said = wordSaidBetween(previous, next);
    if (said !== null) cues.push({ kind: "word-said", said });
    if (turnCameBetween(previous, next)) cues.push({ kind: "turn-came" });
    if (dealtBetween(previous, next)) cues.push({ kind: "dealt" });
    const appeared = resultAppearedBetween(previous, next);
    if (appeared !== null) cues.push(appeared);
    return [...cues, ...nudges];
}

/** The ordinal of the result a page that watched the play receives when the last card ended the hand, else null. */
export function closedHandOrdinal(previous: Table, next: Table): number | null {
    return previous.hand?.playing == null ? null : playedOutResultOrdinal(next);
}

/** The ordinal of the result the table shows when the last card ended its hand, else null. A hand that ended by a give-up or a throw-down has no last trick. */
export function playedOutResultOrdinal(table: Table): number | null {
    const { result } = table;
    if (table.hand !== null || result === null) return null;
    return result.kind === "declared" && result.ending !== "played-out" ? null : result.ordinal;
}

// Each card the update laid, and the trick the completing card finished right after it.
function cardCuesBetween(previous: Table, next: Table): Cue[] {
    const { laid, completed, completing } = cardsLaidBetween(previous, next);
    return laid.flatMap(({ seat, card }, index): Cue[] => {
        const played: Cue = { kind: "card-played", seat, card };
        return index === completing - 1 && completed !== null
            ? [played, { kind: "trick-taken", trick: completed }]
            : [played];
    });
}

function nudgedCuesBetween(previous: Table, next: Table): Cue[] {
    return nudgedChairs(previous, next).map(({ seat, nudge }) => ({
        kind: "nudged",
        seat,
        pick: next.version + seat + nudge.nudges,
    }));
}

export function isChairCue(cue: Cue): cue is ChairCue {
    return cue.kind === "chair-taken" || cue.kind === "chair-stood" || cue.kind === "chair-opened";
}

// The stamp of the word an update brought, or null. A page that has no table before it, as after a reload or a dropped
// connection, stamps nothing: the plaque already tells the word.
export function stampBetween(previous: Table | undefined, next: Table): Stamp | null {
    const said = wordSaidBetween(previous, next);
    return said === null ? null : stampOf(next, said);
}

// Whether the bubble a chair shows is a bid this page saw said in the latest update that brought any, which springs up.
export function springsUp(said: readonly BidSaid[], seat: number, bubble: Bubble | null): boolean {
    return said.some(
        (each) => each.seat === seat && each.word.action === bubble?.kind && each.word.value === bubble.value,
    );
}

// Whether the bid that stands is one this page saw said in the latest update that brought any, to which the counter
// rolls.
export function rollsTo(said: readonly BidSaid[], standing: number | null): boolean {
    return said.some(({ word }) => word.action === "bid" && word.value === standing);
}

// Whether this page saw a chair say „Weg“ in the latest update that brought words, after which another pair bids.
export function pairTurned(said: readonly BidSaid[]): boolean {
    return said.some(({ word }) => word.action === "pass");
}

// A chair that was open and holds someone now was taken. A chair that was held and is open now stood up, and opened for
// the running hand when the hand waits for a sitter in `next`.
function chairCuesBetween(previous: Table, next: Table): ChairCue[] {
    const opensForHand = handWaits(next.hand);
    const tookOpenChair = handWaits(previous.hand);
    return next.chairs.flatMap((after): ChairCue[] => {
        const before = previous.chairs.find((chair) => chair.seat === after.seat) as Chair;
        if (before.occupant_name === null && after.occupant_name !== null)
            return [{ kind: "chair-taken", inHand: tookOpenChair, ...sitterOf(after) }];
        if (before.occupant_name !== null && after.occupant_name === null)
            return [{ kind: opensForHand ? "chair-opened" : "chair-stood", ...sitterOf(before) }];
        return [];
    });
}

// Only a chair that is held is asked who holds it.
function sitterOf(chair: Chair): Sitter {
    return {
        seat: chair.seat,
        name: chair.occupant_name as string,
        agent: chair.occupant_kind === "agent",
        mine: chair.is_mine,
    };
}

// The seat is null while the last trick of a hand rests and sweeps.
type Turn = { phase: "auction" | "declare" | "push" | "play"; seat: number | null };

// Where the hand waits for one chair: the auction's bidder, the declarer who chooses the game, the player of the stage
// before a Ramsch or of the play. A turn is the chair together with that phase, so a chair that acts in two phases in a row
// is on turn twice, and the steps inside one phase make one turn. No chair is on turn while the hand waits for a sitter.
function turnOf(table: Table): Turn | null {
    const hand = table.hand;
    if (hand === null || handWaits(hand)) return null;
    if (hand.playing !== null) return { phase: "play", seat: hand.playing.turn_seat };
    if (hand.pushing !== null) return { phase: "push", seat: hand.pushing.turn_seat };
    if (hand.declaring !== null)
        return hand.declaring.stage === "declared" ? null : { phase: "declare", seat: hand.declaring.declarer_seat };
    return hand.auction.awaiting === null ? null : { phase: "auction", seat: hand.auction.turn_seat as number };
}

function turnCameBetween(previous: Table, next: Table): boolean {
    const own = next.chairs.find((chair) => chair.is_mine);
    const now = turnOf(next);
    if (own === undefined || now?.seat !== own.seat) return false;
    const before = turnOf(previous);
    return before?.seat !== now.seat || before.phase !== now.phase;
}

// A hand is dealt when a table without one gets one, or when the dealer changes from hand to hand.
function dealtBetween(previous: Table, next: Table): boolean {
    return next.hand !== null && previous.hand?.dealer_seat !== next.hand.dealer_seat;
}

// The declared result that the update brings to a page that watches; a page that opens later or reconnects sees the
// result as it stands, so it has none.
function resultAppearedBetween(previous: Table, next: Table): Extract<Cue, { kind: "result-appeared" }> | null {
    const result = declaredResult(next);
    if (result === null || previous.result?.ordinal === result.ordinal) return null;
    return {
        kind: "result-appeared",
        ordinal: result.ordinal,
        won: resultIsGood(result, next.chairs),
        counts: result.gains.some((seat) => seat.gain > 0),
    };
}

// The word the update from `previous` to `next` brought, the last when it brought several.
function wordSaidBetween(previous: Table | undefined, next: Table): SaidWord | null {
    if (previous === undefined || next.version <= previous.version) return null;
    const before = previous.hand?.playing?.kontra?.said ?? [];
    const after = next.hand?.playing?.kontra?.said ?? [];
    return after.length > before.length ? (after.at(-1) as SaidWord) : null;
}

// The auction tells every word in the order it was said, so the words past the ones this page has seen were said in
// this update: the one step a player took, or each step the table took for the plans. A play shows nothing at the
// table, so it is no cue.
function bidsSaidBetween(previous: Table, next: Table): BidSaid[] {
    const before = previous.hand?.auction.steps ?? [];
    const said = next.hand?.auction.steps ?? [];
    const seen = sameJson(said.slice(0, before.length), before) ? before.length : 0;
    return said
        .slice(seen)
        .filter((word) => word.action !== "play")
        .map((word) => ({ seat: word.seat, word: { action: word.action as BidWord["action"], value: word.value } }));
}

// A request ends without a card, a chair change or a game end when the felt and the chairs stay as they were.
function requestEndedWhileTheGameWentOn(previous: Table, next: Table): boolean {
    const before = previous.hand?.playing;
    const after = next.hand?.playing;
    return (
        !!before &&
        !!after &&
        sameJson(before.current_trick, after.current_trick) &&
        sameJson(before.last_trick, after.last_trick) &&
        sameJson(
            previous.chairs.map((chair) => chair.occupant_name),
            next.chairs.map((chair) => chair.occupant_name),
        )
    );
}

// The second no clears the declarer's request that already carried the first no, while the game goes on with the same
// cards on the felt and the same people in the chairs; a card, a yes and a chair that changed hands clear it otherwise.
function giveUpRefusedBetween(previous: Table, next: Table): number[] | null {
    const asked = previous.hand?.playing?.give_up;
    if (typeof asked?.declined_seat !== "number" || next.hand?.playing?.give_up !== null) return null;
    return requestEndedWhileTheGameWentOn(previous, next)
        ? next.chairs.map((chair) => chair.seat).filter((seat) => seat !== asked.asking_seat)
        : null;
}

// One no ends a shortening and names its opponent; the game goes on with the same cards on the felt.
function shorteningRefusedBetween(previous: Table, next: Table): number | null {
    const refuser = next.hand?.playing?.shortening_refused_seat ?? null;
    if (!previous.hand?.playing?.shortening || next.hand?.playing?.shortening !== null || refuser === null) return null;
    return requestEndedWhileTheGameWentOn(previous, next) ? refuser : null;
}

// The declarer's no to a wrong open play ends the request and leaves that opponent's cards open.
function openPlayPlayedOnBetween(previous: Table, next: Table): number | null {
    const player = previous.hand?.playing?.open_play_seat ?? null;
    const after = next.hand?.playing;
    if (player === null || after?.open_play_seat !== null) return null;
    const opened = after.open_hands.some((hand) => hand.seat === player);
    return opened && requestEndedWhileTheGameWentOn(previous, next) ? player : null;
}

// The auction ended in the update that brings the declaring to a hand that had none; a page that opens later
// or reconnects sees the choosing as it is.
function auctionJustEnded(previous: Table, next: Table): boolean {
    return !!previous.hand && !previous.hand.declaring && next.hand?.declaring?.stage === "choosing";
}

// The first `completing` of the cards laid finished the `completed` trick; the cards after them lead the next.
type TrickStep = { laid: SeatedCard[]; completed: LastTrick | null; completing: number };
const NO_STEP: TrickStep = { laid: [], completed: null, completing: 0 };

// The cards this update laid on the felt, in the order they were laid, and the trick they completed if any; nothing
// unless every change is explained.
function cardsLaidBetween(previous: Table, next: Table): TrickStep {
    const before = previous.hand?.playing;
    const after = next.hand?.playing;
    if (!before || !after) return NO_STEP;
    const step = trickStepBetween(before, after, next.chairs);
    return step !== null && handCountsExplain(previous.chairs, next.chairs, step.laid) ? step : NO_STEP;
}

// Either the trick on the felt grew, or it completed: then the cards of it that the page has not seen laid, and the
// cards on the new trick, are laid.
function trickStepBetween(before: Playing, after: Playing, chairs: Chair[]): TrickStep | null {
    if (sameJson(before.last_trick, after.last_trick)) {
        const added = cardsAddedToTrick(before.current_trick, after.current_trick);
        return added === null ? null : { laid: added, completed: null, completing: 0 };
    }
    const completed = after.last_trick;
    if (completed === null) return null;
    const completing = completingCards(before.current_trick, chairs, completed);
    return completing === null
        ? null
        : { laid: [...completing, ...after.current_trick], completed, completing: completing.length };
}

function cardsAddedToTrick(before: SeatedCard[], after: SeatedCard[]): SeatedCard[] | null {
    return sameJson(after.slice(0, before.length), before) ? after.slice(before.length) : null;
}

// The trick's cards carry no seats, so they go round the table from the leader. The cards the page saw on the felt
// are its first, and the rest completed it, which may be more than one when the page missed an update.
function completingCards(seen: SeatedCard[], chairs: Chair[], completed: LastTrick): SeatedCard[] | null {
    const seats = seatsInTurnFrom(chairs, completed.leader_seat);
    const trick = completed.cards.map((card, index) => ({ seat: seats[index] as number, card }));
    const explained =
        trick.length === SEATS_AT_A_TABLE &&
        sameJson(
            completed.cards.slice(0, seen.length),
            seen.map((seated) => seated.card),
        );
    return explained ? trick.slice(seen.length) : null;
}

// Each card laid takes one card from its player's hand, and no other hand changes.
function handCountsExplain(before: Chair[], after: Chair[], laid: SeatedCard[]): boolean {
    return after.every(
        (chair) =>
            cardCountOf(before, chair.seat) - laid.filter((seated) => seated.seat === chair.seat).length ===
            cardCountOf(after, chair.seat),
    );
}

// Every chair holds a hand while a hand is played, so its count is there to read.
function cardCountOf(chairs: Chair[], seat: number): number {
    return ((chairs.find((chair) => chair.seat === seat) as Chair).hand as ChairHand).card_count;
}

// The server sends one trick and one hand the same way every time, so their JSON is the comparison of their content.
function sameJson(first: unknown, second: unknown): boolean {
    return JSON.stringify(first) === JSON.stringify(second);
}
