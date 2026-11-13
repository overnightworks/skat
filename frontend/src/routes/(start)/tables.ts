import { isFramedInCallMode } from "#lib/callFrame.ts";
import { openStream } from "#lib/stream.ts";
import { handWaits, type SeatNotice } from "#lib/openChair.ts";
import {
    type AUCTION_ACTION_TOKENS,
    AUTH_START_PATH,
    type ANNOUNCEMENT_TOKENS,
    type LEVEL_TOKENS,
    type GAME_TOKENS,
    type AWAITING_TOKENS,
    type BOCK_OVERLAP_TOKENS,
    type BOCK_TRIGGER_TOKENS,
    type DURCHMARSCH_TOKENS,
    type END_REASON_TOKENS,
    type GAME_ENDING_TOKENS,
    type GRAND_HAND_TOKENS,
    type JUNGFRAU_TOKENS,
    type KONTRA_DEADLINE_TOKENS,
    type KONTRA_REACH_TOKENS,
    type KONTRA_SAYER_TOKENS,
    type POSITION_TOKENS,
    type PUSHING_RULE_TOKENS,
    type RAMSCH_SCORING_TOKENS,
    type RANK_TOKENS,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
    type STAGE_TOKENS,
    SUIT_TOKENS,
    TABLE_CARD_SUFFIX,
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    TABLE_ABORT_AGREE_SUFFIX,
    TABLE_ABORT_REFUSE_SUFFIX,
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
    TABLE_EVENTS_SUFFIX,
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_KONTRA_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_PUSHING_GRAND_HAND_SUFFIX,
    TABLE_PUSHING_PUSH_SUFFIX,
    TABLE_PUSHING_PUT_BACK_SUFFIX,
    TABLE_PUSHING_TAKE_SUFFIX,
    TABLE_READY_SUFFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
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
export type Card = { suit: Suit; rank: Rank };
export type ChairHand = { position: Position; card_count: number };
export type Declaring = {
    declarer_seat: number;
    stage: Stage;
    declaration: { game: Game; hand: boolean; ouvert: boolean; announcement: Announcement } | null;
    open_cards: Card[];
};
export type Awaiting = (typeof AWAITING_TOKENS)[number];
export type AuctionAction = (typeof AUCTION_ACTION_TOKENS)[number];
export type AuctionWord = { seat: number; action: AuctionAction; value: number | null };
export type Auction = {
    turn_seat: number | null;
    facing_seat: number | null;
    awaiting: Awaiting | null;
    standing: number | null;
    values: number[];
    words: AuctionWord[];
    declared: { seat: number; value: number } | null;
};
export type SeatedCard = { seat: number; card: Card };
export type Sides = { declarer: number; opponents: number };
// The last trick's cards lie in playing order from the seat that led it.
export type LastTrick = { cards: Card[]; leader_seat: number; taker_seat: number };
// A give-up the table was asked and has not settled: who asked and which opponent already said no, the same for every viewer.
export type GiveUp = { asking_seat: number; declined_seat: number | null };
// The words said in the running hand and their product, with the word the viewer's own chair may say now (null for
// a watcher and for a chair with none open).
export type Kontra = { said: { seat: number; word: Word }[]; factor: number; my_word: Word | null };
export type Playing = {
    turn_seat: number | null;
    current_trick: SeatedCard[];
    last_trick: LastTrick | null;
    // Only the seated player on turn receives the cards they may play.
    legal_cards: Card[];
    // Both sides' points from completed tricks; null unless the table shows them, and in a Null game and a Ramsch.
    running_points: Sides | null;
    give_up: GiveUp | null;
    // Null at a table without Kontra.
    kontra: Kontra | null;
};
// What a seat that finished its turn of the stage before a Ramsch did with the skat.
export type PushAction = "took" | "pushed";
// The stage before a Ramsch's first card; only the seat on turn that holds twelve cards is told cards, the ones it may
// put back.
export type Pushing = {
    turn_seat: number;
    stage: Stage;
    moves: { seat: number; action: PushAction }[];
    factor: number;
    put_back_cards: Card[];
};
export type Hand = {
    dealer_seat: number;
    own_cards: Card[];
    skat_count: number;
    auction: Auction;
    declaring: Declaring | null;
    playing: Playing | null;
    // The open seat a running hand waits for, the same for every viewer.
    waiting_seat: number | null;
    ramsch: boolean;
    // Set while the stage runs; the Ramsch's play has none.
    pushing: Pushing | null;
    // How often the skat was pushed on unseen and what that multiplies the Ramsch's score by, through the play.
    pushes: number;
    push_factor: number;
    // The seats that said yes to aborting the hand, null while no vote stands; the same for every viewer.
    abort: number[] | null;
    // A chair of the hand is open, so the seated players may vote to abort it.
    abortable: boolean;
};
export type Chair = {
    seat: number;
    occupant_name: string | null;
    occupant_kind: "person" | "agent" | null;
    is_mine: boolean;
    is_away: boolean;
    ready: boolean;
    // The person's running total; null on a free chair and, in a table's first series, until its first result;
    // a later series reads 0 from its first deal.
    total: number | null;
    hand: ChairHand | null;
    // Whoever held the chair in the running hand and left it, while it stays open; the same for every viewer.
    former_holder_name: string | null;
    // True only on the chair of the running hand that the viewer stood up from, open or taken since: the one chair they
    // may sit in again.
    is_mine_to_return: boolean;
};
export type RamschSeat = { seat: number; points: number; score: number };
// The finished Ramsch as the server counted it: what each seat's counted eyes were and what it added, the sweeper of a
// Durchmarsch, and the factors the losers' score carries.
export type RamschResult = {
    kind: "ramsch";
    ordinal: number;
    seats: RamschSeat[];
    durchmarsch_seat: number | null;
    jungfrau: boolean;
    bock_factor: number;
    pushes: number;
    push_factor: number;
    // The eyes were divided by ten before the factors.
    divided_by_ten: boolean;
};
export type SeatGain = { seat: number; gain: number; won: boolean };
// The finished game as the server counted it; the page draws these numbers and decides no rule.
export type Result = {
    kind: "declared";
    ordinal: number;
    declarer_seat: number;
    game: Game;
    hand: boolean;
    ouvert: boolean;
    announcement: Announcement;
    // Null has no matadors, base value or multiplier.
    matadors: { mit: boolean; count: number } | null;
    base_value: number | null;
    levels: Level[];
    multiplier: number | null;
    list_bonus: number;
    announcement_missed: boolean;
    won: boolean;
    doubled: boolean;
    overbid: boolean;
    bid: number;
    game_value: number;
    settled_value: number;
    score: number;
    declarer_points: number;
    opponents_points: number;
    gains: SeatGain[];
    // What the Bock rounds multiplied the list score by; 1 outside a Bock game.
    bock_factor: number;
    // The last word said and the factor it doubled the score by; null when no word was said.
    kontra: { word: Word; factor: number } | null;
    // How the game ended, and the seat whose give-up or throw-down ended it; null exactly when it was played out.
    ending: GameEnding;
    ended_by_seat: number | null;
};
// Set between hands after three passes; the next dealer is named only while all three chairs are occupied.
export type PassedIn = { next_dealer_seat: number | null };
export type EndReason = (typeof END_REASON_TOKENS)[number];
// Why a table ended with the one fact stored when it ended: the whole seconds nobody was there, or the days nobody played.
export type Ended =
    | { reason: Extract<EndReason, "empty">; empty_seconds: number; unplayed_days: null }
    | { reason: Extract<EndReason, "unplayed">; empty_seconds: null; unplayed_days: number };
// The rules a table was opened with, answered to every viewer; a rule that is off is null.
export type Options = {
    show_running_points: boolean;
    kontra: {
        sayer: (typeof KONTRA_SAYER_TOKENS)[number];
        reach: (typeof KONTRA_REACH_TOKENS)[number];
        deadline: (typeof KONTRA_DEADLINE_TOKENS)[number];
    } | null;
    bock: { triggers: (typeof BOCK_TRIGGER_TOKENS)[number][]; overlap: (typeof BOCK_OVERLAP_TOKENS)[number] } | null;
    ramsch: {
        scoring: (typeof RAMSCH_SCORING_TOKENS)[number];
        jungfrau: (typeof JUNGFRAU_TOKENS)[number];
        durchmarsch: (typeof DURCHMARSCH_TOKENS)[number];
        pushing: { rule: (typeof PUSHING_RULE_TOKENS)[number]; grand_hand: (typeof GRAND_HAND_TOKENS)[number] } | null;
    } | null;
};
// The Bock games still to come, the running one included, and what the running or next game's list score is multiplied
// by; the same for every viewer. A table without Bock has none.
export type Bock = { games_left: number; factor: number };
export type Table = {
    id: string;
    version: number;
    chairs: Chair[];
    watchers: number;
    hand: Hand | null;
    result: Result | RamschResult | null;
    passed_in: PassedIn | null;
    // Set between hands after a vote aborted the hand, with the next dealer as a passed-in hand names it.
    aborted: PassedIn | null;
    // Null once the table has ended.
    options: Options | null;
    bock: Bock | null;
    ended: Ended | null;
};
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
async function ask(path: string, init?: RequestInit): Promise<Outcome> {
    const answer = await fetchSigningInAgain(path, init);
    if (answer === null) return { kind: "failed" };
    if (answer.status === NOT_FOUND_STATUS) return { kind: "missing" };
    try {
        const body: unknown = await answer.json();
        if (answer.ok) return { kind: "table", table: body as Table };
        // Any other refusal means the page showed a stale table: its stream is about to correct it.
        if (answer.status === CONFLICT_STATUS && isTakenChair(body)) return { kind: "taken", holder: body.holder_name };
        return { kind: "failed" };
    } catch {
        return { kind: "failed" };
    }
}

// The command id is the retry key: asking again with the same one, the same length and the same options returns the
// table the first ask opened. A table opened without options plays the official rules.
export function createTable(
    commandId: string,
    seriesLength: number,
    options?: { show_running_points: boolean },
): Promise<Outcome> {
    return ask(TABLES_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command_id: commandId, series_length: seriesLength, options }),
    });
}

function post(id: string, suffix: string, body: object): Promise<Outcome> {
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

// The version is the one the page shows, so a give-up on a table that has since moved on is refused; there is no retry.
export function giveUp(id: string, version: number, commandId: string): Promise<Outcome> {
    return post(id, TABLE_GIVE_UP_SUFFIX, { command_id: commandId, version });
}

export type GiveUpAnswer = "agree" | "decline";

const GIVE_UP_ANSWER_SUFFIXES: Record<GiveUpAnswer, string> = {
    agree: TABLE_GIVE_UP_AGREE_SUFFIX,
    decline: TABLE_GIVE_UP_DECLINE_SUFFIX,
};

// The version is the one the page shows, so an answer to a request that has since gone is refused; there is no retry.
export function answerGiveUp(id: string, version: number, commandId: string, answer: GiveUpAnswer): Promise<Outcome> {
    return post(id, GIVE_UP_ANSWER_SUFFIXES[answer], { command_id: commandId, version });
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

// „Weiter“ names the result it saw, so a tap on a result that has since been replaced is refused.
export function markReady(id: string, commandId: string, ordinal: number): Promise<Outcome> {
    return post(id, TABLE_READY_SUFFIX, { command_id: commandId, ordinal });
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
): () => void {
    const reachedNow = reachedBySigningIn;
    const path = `${TABLES_PATH}/${encodeURIComponent(id)}`;
    return openStream(`${path}${TABLE_EVENTS_SUFFIX}`, {
        events: {
            message: (data, end) => {
                const table = JSON.parse(data) as Table;
                // An ended table sends nothing more: the stream closes here, so it never reconnects to a table that has ended.
                if (table.ended !== null) end();
                onTable(table);
            },
            attention: (data) => {
                onAttention(JSON.parse(data) as number);
            },
        },
        sessionPath: path,
        onConnection,
        onRefused: () => {
            signInAgain(id, reachedNow);
        },
    });
}

export function tablePath(id: string): string {
    return `${TABLE_PAGE_PREFIX}${id}`;
}

// The sentence that names an agent who sat down between two streamed views: a chair that was free and now holds an agent.
// A chair that was open in the running hand is not this note's: the sitter there is told as one who plays on.
export function agentSitsNote(previous: Table, table: Table): SeatNotice | null {
    if (handWaits(previous.hand)) return null;
    const freed = new Set(previous.chairs.filter((chair) => chair.occupant_name === null).map((chair) => chair.seat));
    const sat = table.chairs.find((chair) => chair.occupant_kind === "agent" && freed.has(chair.seat));
    const name = sat?.occupant_name ?? null;
    return name === null ? null : { text: words["table.agentSits"]({ name }), initials: [null] };
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
