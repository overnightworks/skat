import { isFramedInCallMode } from "#lib/callFrame.ts";
import {
    type AUCTION_ACTION_TOKENS,
    AUTH_START_PATH,
    type ANNOUNCEMENT_TOKENS,
    type LEVEL_TOKENS,
    type GAME_TOKENS,
    type AWAITING_TOKENS,
    type POSITION_TOKENS,
    type RANK_TOKENS,
    RETURN_PATH_QUERY_NAME,
    SIGNED_IN_AGAIN_QUERY_NAME,
    type STAGE_TOKENS,
    SUIT_TOKENS,
    TABLE_CARD_SUFFIX,
    TABLE_DECLARING_DECLARE_SUFFIX,
    TABLE_DECLARING_PUT_BACK_SUFFIX,
    TABLE_DECLARING_TAKE_SUFFIX,
    TABLE_AUCTION_BID_SUFFIX,
    TABLE_AUCTION_HOLD_SUFFIX,
    TABLE_AUCTION_PASS_SUFFIX,
    TABLE_AUCTION_PLAY_SUFFIX,
    TABLE_EVENTS_SUFFIX,
    TABLE_PAGE_PREFIX,
    TABLE_READY_SUFFIX,
    TABLE_SIT_SUFFIX,
    TABLE_STAND_SUFFIX,
    TABLES_PATH,
} from "#lib/wire.ts";
import { words } from "#lib/words.ts";

const SIGNED_OUT_STATUS = 401;
const NOT_FOUND_STATUS = 404;
const CONFLICT_STATUS = 409;
export const SKAT_SIZE = 2;
// A refusal this soon after the page was reached through an automatic sign-in shows the sign-in page instead
// of navigating again: a session the sign-in just made and the server refuses at once would otherwise loop forever.
const RESIGN_IN_WINDOW_MILLISECONDS = 30_000;

export type Suit = (typeof SUIT_TOKENS)[number];
export type Rank = (typeof RANK_TOKENS)[number];
export type Position = (typeof POSITION_TOKENS)[number];
export type Game = (typeof GAME_TOKENS)[number];
export type Announcement = (typeof ANNOUNCEMENT_TOKENS)[number];
export type Level = (typeof LEVEL_TOKENS)[number];
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
export type Playing = {
    turn_seat: number | null;
    current_trick: SeatedCard[];
    last_trick: LastTrick | null;
    // Only the seated player on turn receives the cards they may play.
    legal_cards: Card[];
};
export type Hand = {
    dealer_seat: number;
    own_cards: Card[];
    skat_count: number;
    auction: Auction;
    declaring: Declaring | null;
    playing: Playing | null;
};
export type Chair = {
    seat: number;
    occupant_name: string | null;
    is_mine: boolean;
    is_away: boolean;
    ready: boolean;
    // The person's running total; null on a free chair and until the table's first result.
    total: number | null;
    hand: ChairHand | null;
};
export type SeatGain = { seat: number; gain: number; won: boolean };
// The finished game as the server counted it; the page draws these numbers and decides no rule.
export type Result = {
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
};
// Set between hands after three passes; the next dealer is named only while all three chairs are occupied.
export type PassedIn = { next_dealer_seat: number | null };
export type Table = {
    id: string;
    version: number;
    chairs: Chair[];
    watchers: number;
    hand: Hand | null;
    result: Result | null;
    passed_in: PassedIn | null;
};
// A chair that was taken: `holder` is who sits there now.
export type Outcome =
    { kind: "table"; table: Table } | { kind: "taken"; holder: string } | { kind: "missing" } | { kind: "failed" };

function isTakenChair(body: unknown): body is { reason: "seat-taken"; holder_name: string } {
    return typeof body === "object" && body !== null && "reason" in body && body.reason === "seat-taken";
}

// A session that ended while the page was open goes through the sign-in again; any other failure
// is shown to the person as it is, and nothing is retried behind their back.
async function ask(path: string, init?: RequestInit): Promise<Outcome> {
    let answer: Response;
    try {
        answer = await fetch(path, init);
    } catch {
        return { kind: "failed" };
    }
    if (answer.status === SIGNED_OUT_STATUS) {
        location.reload();
        return { kind: "failed" };
    }
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

// The command id is the retry key: asking again with the same one and the same length returns the table the first ask opened.
export function createTable(commandId: string, seriesLength: number): Promise<Outcome> {
    return ask(TABLES_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command_id: commandId, series_length: seriesLength }),
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

// The client names only the card: the seat that plays it comes from the session.
export function playCard(id: string, version: number, commandId: string, card: Card): Promise<Outcome> {
    return post(id, TABLE_CARD_SUFFIX, { command_id: commandId, version, suit: card.suit, rank: card.rank });
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

// A stream that ends is a refused session or a dropped connection; the table's own session check tells
// them apart. Only a 401 signs in again: a drop, or any other answer, leaves the stream to reconnect.
async function sessionIsRefused(id: string): Promise<boolean> {
    try {
        return (await fetch(`${TABLES_PATH}/${encodeURIComponent(id)}`)).status === SIGNED_OUT_STATUS;
    } catch {
        // The connection is down: the dimmed page and the stream's own reconnect carry on.
        return false;
    }
}

// The server sends the full view first and a fresh one after every change; a lost connection
// reconnects by itself and starts again from a full view, so a view always replaces the last.
// The returned function closes the stream.
export function watchTable(
    id: string,
    onTable: (table: Table) => void,
    onConnection: (connected: boolean) => void,
): () => void {
    const reachedNow = reachedBySigningIn;
    const source = new EventSource(`${TABLES_PATH}/${encodeURIComponent(id)}${TABLE_EVENTS_SUFFIX}`);
    source.onmessage = (event: MessageEvent<string>) => {
        onConnection(true);
        onTable(JSON.parse(event.data) as Table);
    };
    // One check at a time, and none counts once the page navigates or stops watching: a second 401 would
    // otherwise reload under the loop guard and cancel the sign-in navigation that the first one started.
    let checking = false;
    let finished = false;
    source.onerror = () => {
        onConnection(false);
        if (checking || finished) return;
        checking = true;
        void sessionIsRefused(id).then((refused) => {
            checking = false;
            if (!refused || finished) return;
            finished = true;
            source.close();
            signInAgain(id, reachedNow);
        });
    };
    return () => {
        finished = true;
        source.close();
    };
}

export function tablePath(id: string): string {
    return `${TABLE_PAGE_PREFIX}${id}`;
}

// The seats in drawing order: the viewer's own chair comes last, which is the one at the bottom.
export function drawingOrder(chairs: Chair[]): Chair[] {
    const afterMine = chairs.findIndex((chair) => chair.is_mine) + 1;
    return [...chairs.slice(afterMine), ...chairs.slice(0, afterMine)];
}

const POSITION_WORDS: Record<Position, string> = {
    forehand: words.forehand,
    middlehand: words.middlehand,
    rearhand: words.rearhand,
};

// The auction's value, shown to everyone until the game is declared.
export function bidValueWhileDeclaring(table: Table): number | null {
    const hand = table.hand;
    if (!hand?.declaring || hand.declaring.stage === "declared") return null;
    return hand.auction.declared?.value ?? null;
}

// The stage this viewer must act on: only the declarer acts, and only until the game is declared.
export function declarerStage(table: Table): Exclude<Stage, "declared"> | null {
    const declaring = table.hand?.declaring;
    if (!declaring || declaring.stage === "declared") return null;
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
export type Picking = { picked: readonly Card[]; disabled: boolean; toggle: (card: Card) => void };

const GAME_WORDS: Record<Game, string> = {
    karo: words.gameKaro,
    herz: words.gameHerz,
    pik: words.gamePik,
    kreuz: words.gameKreuz,
    grand: words.gameGrand,
    null: words.gameNull,
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
    if (announcement === "schneider") return words.announcedSchneider;
    return announcement === "schwarz" ? words.announcedSchwarz : null;
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
    if (ouvert) {
        const handSuffix = game === "null" && hand ? ` ${words.hand}` : "";
        return { name: `${gameWord(game)} ${words.ouvert}${handSuffix}`, announcement: null };
    }
    const name = hand ? `${gameWord(game)} ${words.hand}` : gameWord(game);
    return { name, announcement: announcedWord(announcement) };
}

const RANK_WORDS: Record<Rank, string> = {
    seven: words.rankSeven,
    eight: words.rankEight,
    nine: words.rankNine,
    ten: words.rankTen,
    jack: words.rankJack,
    queen: words.rankQueen,
    king: words.rankKing,
    ace: words.rankAce,
};

// A card's own name: a suit's word is the word of the game of that suit.
export function cardName(card: Card): string {
    return `${GAME_WORDS[card.suit]} ${RANK_WORDS[card.rank]}`;
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
