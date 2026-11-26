import { isFramedInCallMode } from "#lib/callFrame.ts";
import { openStream, type StreamRefusal } from "#lib/stream.ts";
import { handWaits } from "#lib/openChair.ts";
import { tableOfWire, type WireTable } from "#lib/wireTable.ts";
import {
    type AUCTION_ACTION_TOKENS,
    type CardAnswer,
    type ChairAnswer,
    type OptionsAnswer,
    type EndedAnswer,
    type SeatedCardAnswer,
    type OCCUPANT_KIND_TOKENS,
    type PUSH_ACTION_TOKENS,
    type STOP_OUTCOME_TOKENS,
    type TableAnswer,
    AUTH_START_PATH,
    type ANNOUNCEMENT_TOKENS,
    type LEVEL_TOKENS,
    type GAME_TOKENS,
    type AWAITING_TOKENS,
    type END_REASON_TOKENS,
    type GAME_ENDING_TOKENS,
    type PLAN_KIND_TOKENS,
    type PLAN_MODE_TOKENS,
    type POSITION_TOKENS,
    type RANK_TOKENS,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
    type STAGE_TOKENS,
    type TABLE_STYLE_TOKENS,
    SUIT_TOKENS,
    TABLE_CARD_SUFFIX,
    TABLE_STOP_PLAYING_SUFFIX,
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    TABLE_ABORT_AGREE_SUFFIX,
    TABLE_ABORT_REFUSE_SUFFIX,
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAN_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
    TABLE_EVENTS_SUFFIX,
    TABLE_KONTRA_SUFFIX,
    TABLE_NO_WORD_SUFFIX,
    TABLE_LIST_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_PUSHING_GRAND_HAND_SUFFIX,
    TABLE_PUSHING_PUSH_SUFFIX,
    TABLE_PUSHING_PUT_BACK_SUFFIX,
    TABLE_PUSHING_TAKE_SUFFIX,
    TABLE_SERIES_END_AGREE_SUFFIX,
    TABLE_SERIES_END_REFUSE_SUFFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLE_STYLE_SUFFIX,
    TABLES_PATH,
    type WORD_TOKENS,
} from "#lib/wire.ts";
import { words } from "#lib/words.ts";

const SIGNED_OUT_STATUS = 401;
export const NOT_FOUND_STATUS = 404;
export const CONFLICT_STATUS = 409;
export const SKAT_SIZE = 2;
// A refusal this soon after the page was reached through an automatic sign-in shows the sign-in page instead
// of navigating again: a session the sign-in just made and the server refuses at once would otherwise loop forever.
const RESIGN_IN_WINDOW_MILLISECONDS = 30_000;

export type Suit = (typeof SUIT_TOKENS)[number];
export type Rank = (typeof RANK_TOKENS)[number];
export type Position = (typeof POSITION_TOKENS)[number];
export type Game = (typeof GAME_TOKENS)[number];
export type GameEnding = (typeof GAME_ENDING_TOKENS)[number];
export type Announcement = (typeof ANNOUNCEMENT_TOKENS)[number];
export type Level = (typeof LEVEL_TOKENS)[number];
// The Kontra words in the order they are said.
export type Word = (typeof WORD_TOKENS)[number];
export type Stage = (typeof STAGE_TOKENS)[number];
export type Card = CardAnswer;
export type Chair = ChairAnswer;
export type SeatedCard = SeatedCardAnswer;
export type {
    AuctionAnswer as Auction,
    AuctionPlanAnswer as AuctionPlan,
    AuctionWordAnswer as AuctionWord,
    BockAnswer as Bock,
    ChairHandAnswer as ChairHand,
    DeclaringAnswer as Declaring,
    GiveUpAnswer as GiveUp,
    HandAnswer as Hand,
    KontraAnswer as Kontra,
    LastTrickAnswer as LastTrick,
    NextDealerAnswer as PassedIn,
    NextSettingsAnswer as NextSettings,
    OpenHandAnswer as OpenHand,
    PlayingAnswer as Playing,
    PushingAnswer as Pushing,
    RamschResultAnswer as RamschResult,
    RamschSeatAnswer as RamschSeat,
    ResultAnswer as Result,
    SeatGainAnswer as SeatGain,
    SeriesAnswer as Series,
    SeriesEndProposalAnswer as EndProposal,
    ShorteningAnswer as Shortening,
    SidesAnswer as Sides,
    StandingAnswer as Standing,
    TakenAnswer as Taken,
    TurnStateAnswer as TurnState,
} from "#lib/wire.ts";
export type Awaiting = (typeof AWAITING_TOKENS)[number];
export type AuctionAction = (typeof AUCTION_ACTION_TOKENS)[number];
export type PlanMode = (typeof PLAN_MODE_TOKENS)[number];
export type PlanKind = (typeof PLAN_KIND_TOKENS)[number];
export type Options = OptionsAnswer;
export type PushAction = (typeof PUSH_ACTION_TOKENS)[number];
export type OccupantKind = (typeof OCCUPANT_KIND_TOKENS)[number];
export type StopOutcome = (typeof STOP_OUTCOME_TOKENS)[number];
// A plan as a player sets it; null takes the plan back.
export type PlanChoice = { kind: "limit"; value: number; mode: PlanMode } | { kind: "pass" } | null;
export type EndReason = (typeof END_REASON_TOKENS)[number];
// The page's refinement of the server's flat `EndedAnswer`, which ties two narrowings it does not state: the reason
// decides which of the two counts is a number, and a table that played no game has neither standings nor game count.
type EndedPlayed =
    | { standings: NonNullable<EndedAnswer["standings"]>; game_count: NonNullable<EndedAnswer["game_count"]> }
    | { standings: null; game_count: null };
export type Ended = EndedPlayed &
    (
        | {
              reason: Extract<EndReason, "empty">;
              empty_seconds: NonNullable<EndedAnswer["empty_seconds"]>;
              unplayed_days: null;
              closed_by_name: null;
          }
        | {
              reason: Extract<EndReason, "unplayed">;
              empty_seconds: null;
              unplayed_days: NonNullable<EndedAnswer["unplayed_days"]>;
              closed_by_name: null;
          }
        | {
              reason: Extract<EndReason, "closed">;
              empty_seconds: null;
              unplayed_days: null;
              closed_by_name: EndedAnswer["closed_by_name"];
          }
    );
// What an opener sends: a rule that is off is left out, the running points and the give-up rules only when on.
export type OptionsRequest = { show_running_points?: true; give_up?: OptionsAnswer["give_up"] } & {
    [Rule in "kontra" | "bock" | "ramsch"]?: NonNullable<OptionsAnswer[Rule]>;
};
export type TableStyle = (typeof TABLE_STYLE_TOKENS)[number];

export type Table = Omit<TableAnswer, "ended"> & { ended: Ended | null };
// A chair that was taken: `holder` is who sits there now.
export type Outcome =
    { kind: "table"; table: Table } | { kind: "taken"; holder: string } | { kind: "missing" } | { kind: "failed" };

function isTakenChair(body: unknown): body is { reason: "seat-taken"; holder_name: string } {
    return typeof body === "object" && body !== null && "reason" in body && body.reason === "seat-taken";
}

// The answer is null when the server cannot be reached.
export async function fetchOrNull(path: string, init?: RequestInit): Promise<Response | null> {
    try {
        return await fetch(path, init);
    } catch {
        return null;
    }
}

// A session that ended while the page was open goes through the sign-in again; the answer is null then and when the
// server cannot be reached.
export async function fetchSigningInAgain(path: string, init?: RequestInit): Promise<Response | null> {
    const answer = await fetchOrNull(path, init);
    if (answer?.status === SIGNED_OUT_STATUS) {
        location.reload();
        return null;
    }
    return answer;
}

// Any other failure is shown to the person as it is, and nothing is retried behind their back.
export async function ask(path: string, init?: RequestInit): Promise<Outcome> {
    const answer = await fetchSigningInAgain(path, init);
    if (answer === null) return { kind: "failed" };
    if (answer.status === NOT_FOUND_STATUS) return { kind: "missing" };
    try {
        const body: unknown = await answer.json();
        if (answer.ok) return { kind: "table", table: tableOfWire(body as WireTable) };
        // Any other refusal means the page showed a stale table: its stream is about to correct it.
        if (answer.status === CONFLICT_STATUS && isTakenChair(body)) return { kind: "taken", holder: body.holder_name };
        return { kind: "failed" };
    } catch {
        return { kind: "failed" };
    }
}

export function post(id: string, suffix: string, body: object): Promise<Outcome> {
    return ask(`${TABLES_PATH}/${encodeURIComponent(id)}${suffix}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
}

export function sitDown(id: string, seat: number, commandId: string): Promise<Outcome> {
    return post(id, TABLE_SIT_SUFFIX, { command_id: commandId, seat });
}

export function standUp(id: string, commandId: string): Promise<Outcome> {
    return post(id, TABLE_STAND_SUFFIX, { command_id: commandId });
}

// Ends the table once its series is over; it names nobody afterwards.
export function stopPlaying(id: string, commandId: string): Promise<Outcome> {
    return post(id, TABLE_STOP_PLAYING_SUFFIX, { command_id: commandId });
}

export type DeclaringStep =
    | { action: "take" }
    | { action: "put_back"; cards: readonly Card[] }
    | { action: "declare"; game: Game; hand: boolean; ouvert: boolean; announcement: Announcement };

const DECLARING_STEP_SUFFIXES: Record<DeclaringStep["action"], string> = {
    take: TABLE_DECLARING_TAKE_SUFFIX,
    put_back: TABLE_DECLARING_PUT_BACK_SUFFIX,
    declare: TABLE_DECLARING_DECLARE_SUFFIX,
};

// The version is the one the page shows; each tap brings its own command id, and nothing is retried.
// The action only picks the path: the body carries the step's fields.
export function takeDeclaringStep(
    id: string,
    version: number,
    commandId: string,
    step: DeclaringStep,
): Promise<Outcome> {
    const { action, ...fields } = step;
    return post(id, DECLARING_STEP_SUFFIXES[action], { command_id: commandId, version, ...fields });
}

export type PushingStep =
    { action: "take" } | { action: "put_back"; cards: readonly Card[] } | { action: "push" } | { action: "grand_hand" };

const PUSHING_STEP_SUFFIXES: Record<PushingStep["action"], string> = {
    take: TABLE_PUSHING_TAKE_SUFFIX,
    put_back: TABLE_PUSHING_PUT_BACK_SUFFIX,
    push: TABLE_PUSHING_PUSH_SUFFIX,
    grand_hand: TABLE_PUSHING_GRAND_HAND_SUFFIX,
};

// The version is the one the page shows; each tap brings its own command id, and nothing is retried.
export function takePushingStep(id: string, version: number, commandId: string, step: PushingStep): Promise<Outcome> {
    const { action, ...fields } = step;
    return post(id, PUSHING_STEP_SUFFIXES[action], { command_id: commandId, version, ...fields });
}

// The client names only the card: the seat that plays it comes from the session.
export function playCard(id: string, version: number, commandId: string, card: Card): Promise<Outcome> {
    return post(id, TABLE_CARD_SUFFIX, { command_id: commandId, version, suit: card.suit, rank: card.rank });
}

export type AbortAnswer = "agree" | "refuse";

const ABORT_ANSWER_SUFFIXES: Record<AbortAnswer, string> = {
    agree: TABLE_ABORT_AGREE_SUFFIX,
    refuse: TABLE_ABORT_REFUSE_SUFFIX,
};

// A vote has no version to name, so a yes or no arrives for the state the voter saw and is judged on the chairs as they are.
export function answerAbort(id: string, commandId: string, answer: AbortAnswer): Promise<Outcome> {
    return post(id, ABORT_ANSWER_SUFFIXES[answer], { command_id: commandId });
}

// The word is the one the table offered the viewer; the version is the one the page shows, so a word the table has
// since moved past is refused, and there is no retry.
export function sayKontra(id: string, version: number, commandId: string, word: Word): Promise<Outcome> {
    return post(id, TABLE_KONTRA_SUFFIX, { command_id: commandId, version, word });
}

// The viewer's seat gives up the word it owes before the first card; the table stops asking it and the word is gone.
export function sayNoWord(id: string, version: number, commandId: string): Promise<Outcome> {
    return post(id, TABLE_NO_WORD_SUFFIX, { command_id: commandId, version });
}

// A seated person gives the table a style; the stream brings it to every page at the table, so the answer's table is
// not shown.
export function chooseStyle(id: string, commandId: string, style: TableStyle): Promise<Outcome> {
    return post(id, TABLE_STYLE_SUFFIX, { command_id: commandId, style });
}

export type SeriesEndAnswer = "agree" | "refuse";

const SERIES_END_ANSWER_SUFFIXES: Record<SeriesEndAnswer, string> = {
    agree: TABLE_SERIES_END_AGREE_SUFFIX,
    refuse: TABLE_SERIES_END_REFUSE_SUFFIX,
};

// A yes proposes the end when none stands and accepts it when one does; neither names a version, so the answer is judged
// on the table as it is.
export function answerSeriesEnd(id: string, commandId: string, answer: SeriesEndAnswer): Promise<Outcome> {
    return post(id, SERIES_END_ANSWER_SUFFIXES[answer], { command_id: commandId });
}

const AUCTION_STEP_SUFFIXES: Record<AuctionAction, string> = {
    bid: TABLE_AUCTION_BID_SUFFIX,
    hold: TABLE_AUCTION_HOLD_SUFFIX,
    pass: TABLE_AUCTION_PASS_SUFFIX,
    play: TABLE_AUCTION_PLAY_SUFFIX,
};

// The version is the one the page shows, so a step taken on a stale page is refused; there is no retry.
export function takeAuctionStep(
    id: string,
    commandId: string,
    version: number,
    action: AuctionAction,
    value?: number,
): Promise<Outcome> {
    return post(id, AUCTION_STEP_SUFFIXES[action], { command_id: commandId, version, value });
}

// A plan names no version: one made off turn must not race another player's step.
export function setAuctionPlan(id: string, commandId: string, plan: PlanChoice): Promise<Outcome> {
    return post(id, TABLE_AUCTION_PLAN_SUFFIX, { command_id: commandId, plan });
}

export function readTable(id: string): Promise<Outcome> {
    takeSignedInAgainMarker();
    return ask(`${TABLES_PATH}/${encodeURIComponent(id)}`);
}

// The page that the sign-in returns to carries a marker in its address, so nothing is kept on the device.
// The reload of a table address is answered with the sign-in page while the session stays ended.
// A framed call-mode page reloads too: the issuer refuses to be framed, and the gate leads the frame to the
// call sign-in page, where one tap signs in through a separate window.
function signInAgain(id: string, reachedBySigningIn: boolean): void {
    if (isFramedInCallMode() || (reachedBySigningIn && performance.now() < RESIGN_IN_WINDOW_MILLISECONDS)) {
        location.reload();
        return;
    }
    const returnPath = `${tablePath(id)}?${SIGNED_IN_AGAIN_QUERY_NAME}=1`;
    location.assign(`${AUTH_START_PATH}?${RETURN_PATH_QUERY_NAME}=${encodeURIComponent(returnPath)}`);
}

let reachedBySigningIn = false;

// The marker is taken at the page's first table request, whatever the answer, and then leaves the address
// bar, so a reload, a bookmark or a shared link never carries it. Later calls find it gone and keep the result.
function takeSignedInAgainMarker(): void {
    const address = new URL(location.href);
    if (!address.searchParams.has(SIGNED_IN_AGAIN_QUERY_NAME)) return;
    address.searchParams.delete(SIGNED_IN_AGAIN_QUERY_NAME);
    history.replaceState(history.state, "", address);
    reachedBySigningIn = true;
}

const ATTENTION_CAP = 9;

// The digit on the Lobby button: none when no other table waits, "9+" above nine.
export function attentionMark(count: number): string {
    if (count === 0) return "";
    return count > ATTENTION_CAP ? `${String(ATTENTION_CAP)}+` : String(count);
}

// The server sends the full view first and a fresh one after every change; the event `attention` carries the
// number of the person's other tables that wait for him, and is sent at the start and whenever the number changes.
// The stream reader reconnects by itself after a lost or ended stream, and each new stream starts from a full view
// and a full count, so a view replaces the last. The returned function closes the stream.
export function watchTable(
    id: string,
    onTable: (table: Table) => void,
    onAttention: (count: number) => void,
    onConnection: (connected: boolean) => void,
    onRefusal: (refusal: Exclude<StreamRefusal, "signedOut">) => void,
): () => void {
    const reachedNow = reachedBySigningIn;
    const path = `${TABLES_PATH}/${encodeURIComponent(id)}`;
    return openStream(`${path}${TABLE_EVENTS_SUFFIX}`, {
        events: {
            message: (data, end) => {
                const table = tableOfWire(JSON.parse(data) as WireTable);
                // An ended table sends nothing more: the stream closes here, so it never reconnects to a table that has ended.
                if (table.ended !== null) end();
                onTable(table);
            },
            attention: (data) => {
                onAttention(JSON.parse(data) as number);
            },
        },
        onConnection,
        onRefused: (refusal) => {
            if (refusal === "signedOut") signInAgain(id, reachedNow);
            else onRefusal(refusal);
        },
    });
}

export function tablePath(id: string): string {
    return `${TABLE_PAGE_PREFIX}${id}`;
}

// What the agents' control re-reads on: the agents by seat and name, and the version when the wake skipped versions,
// which a swap of two agents of one name in one chair hides in the names; each version is read once.
// A JSON tuple keeps a name that looks like a version from reading as one.
export function seatedAgentsKey(previous: Table | undefined, table: Table): string {
    const agents = table.chairs
        .filter((chair) => chair.occupant_kind === "agent")
        .map((chair) => [chair.seat, chair.occupant_name]);
    const skipped = previous !== undefined && table.version > previous.version + 1;
    return JSON.stringify([agents, skipped ? table.version : null]);
}

// The seats in drawing order: the viewer's own chair comes last, which is the one at the bottom. A viewer who stood up
// from a chair of the running hand keeps the table as it was, with that chair at the bottom.
export function drawingOrder(chairs: Chair[]): Chair[] {
    const afterMine = chairs.findIndex((chair) => chair.is_mine || chair.is_mine_to_return) + 1;
    return [...chairs.slice(afterMine), ...chairs.slice(0, afterMine)];
}

const POSITION_WORDS: Record<Position, string> = {
    forehand: words["game.forehand"],
    middlehand: words["game.middlehand"],
    rearhand: words["game.rearhand"],
};

// The auction's value as the plaque says it, shown to everyone until the game is declared.
export function bidLineWhileDeclaring(table: Table): string | null {
    const hand = table.hand;
    if (!hand?.declaring || hand.declaring.stage === "declared") return null;
    const value = hand.auction.declared?.value;
    return value === undefined ? null : words["table.bidValue"]({ value: String(value) });
}

// The stage this viewer must act on: only the declarer acts, and only until the game is declared and while the hand
// does not wait for a sitter.
export function declarerStage(table: Table): Exclude<Stage, "declared"> | null {
    const declaring = table.hand?.declaring;
    if (!declaring || declaring.stage === "declared" || handWaits(table.hand)) return null;
    const mine = table.chairs.some((chair) => chair.is_mine && chair.seat === declaring.declarer_seat);
    return mine ? declaring.stage : null;
}

function sameCard(first: Card, second: Card): boolean {
    return first.suit === second.suit && first.rank === second.rank;
}

// A tap picks a card or puts a picked one back; a third card stays where it is while two are picked.
export function togglePicked(picked: readonly Card[], card: Card): Card[] {
    if (includesCard(picked, card)) return picked.filter((held) => !sameCard(held, card));
    return picked.length < SKAT_SIZE ? [...picked, card] : [...picked];
}

export function includesCard(cards: readonly Card[], card: Card): boolean {
    return cards.some((held) => sameCard(held, card));
}

// What the hand needs while the declarer picks two cards from the twelve.
// `allowed` names the cards that may be picked; a card outside it is dimmed and not tappable, and without it every card may.
export type Picking = {
    picked: readonly Card[];
    disabled: boolean;
    toggle: (card: Card) => void;
    allowed?: readonly Card[];
};

const GAME_WORDS: Record<Game, string> = {
    karo: words["game.karo"],
    herz: words["game.herz"],
    pik: words["game.pik"],
    kreuz: words["game.kreuz"],
    grand: words["game.grand"],
    null: words["game.null"],
};

const SUIT_GAMES: ReadonlySet<Game> = new Set(SUIT_TOKENS);

// A suit game is named by its trump suit; Grand and Null are not.
export function isSuitGame(game: Game): game is Suit {
    return SUIT_GAMES.has(game);
}

export function gameWord(game: Game): string {
    return GAME_WORDS[game];
}

// The announcement's own words; no announcement has none.
export function announcedWord(announcement: Announcement): string | null {
    if (announcement === "schneider") return words["game.announcedSchneider"];
    return announcement === "schwarz" ? words["game.announcedSchwarz"] : null;
}

// The one name of a declared game, with its levels: „Grand Hand“. A suit or Grand ouvert game includes Hand, so it
// names the game alone; Null ouvert is a game of its own, and with Hand it reads „Null ouvert Hand“. The announcement
// stands apart from the name as its own words; an ouvert game's name already says the Schwarz it counts as, so it has none.
export function gameLabel({
    game,
    hand,
    ouvert,
    announcement,
}: {
    game: Game;
    hand: boolean;
    ouvert: boolean;
    announcement: Announcement;
}): { name: string; announcement: string | null } {
    const gaps = { game: gameWord(game) };
    if (ouvert) {
        const name = game === "null" && hand ? words["game.ouvertHandName"](gaps) : words["game.ouvertName"](gaps);
        return { name, announcement: null };
    }
    const name = hand ? words["game.handName"](gaps) : gaps.game;
    return { name, announcement: announcedWord(announcement) };
}

const RANK_WORDS: Record<Rank, string> = {
    seven: words["game.rankSeven"],
    eight: words["game.rankEight"],
    nine: words["game.rankNine"],
    ten: words["game.rankTen"],
    jack: words["game.rankJack"],
    queen: words["game.rankQueen"],
    king: words["game.rankKing"],
    ace: words["game.rankAce"],
};

// A card's own name: a suit's word is the word of the game of that suit.
export function cardName(card: Card): string {
    return words["game.cardName"]({ suit: GAME_WORDS[card.suit], rank: RANK_WORDS[card.rank] });
}

export function positionWord(position: Position): string {
    return POSITION_WORDS[position];
}

export async function copyTableLink(id: string): Promise<boolean> {
    try {
        await navigator.clipboard.writeText(`${location.origin}${tablePath(id)}`);
        return true;
    } catch {
        return false;
    }
}

export type CardState = "played" | "put-away" | "unplayed";
// One finished game of the series as the server opens it: what it counted and, unless it was finished before games kept
// their cards, every card of it. A trick the end of the game interrupted has fewer than three cards and no taker.
export type GameSheet = {
    number: number;
    seat_names: (string | null)[];
    count:
        | {
              kind: "declared";
              declarer_seat: number;
              declarer_points: number;
              opponents_points: number;
              ending: GameEnding;
              ended_by_seat: number | null;
          }
        | { kind: "ramsch"; seat_points: number[]; durchmarsch_seat: number | null };
    cards: {
        hands: { seat: number; cards: { card: Card; state: CardState }[] }[];
        skat: Card[];
        laid_skat: Card[];
        put_away: SeatedCard[];
        tricks: { number: number; cards: SeatedCard[]; taker_seat: number | null; points: number | null }[];
        skat_takers: number[];
    } | null;
};

// The `number`th game of the current series; null when it cannot be read.
export async function readGameSheet(id: string, number: number): Promise<GameSheet | null> {
    const answer = await fetchSigningInAgain(
        `${TABLES_PATH}/${encodeURIComponent(id)}${TABLE_LIST_SUFFIX}/${String(number)}`,
    );
    if (answer?.ok !== true) return null;
    try {
        return (await answer.json()) as GameSheet;
    } catch {
        return null;
    }
}
