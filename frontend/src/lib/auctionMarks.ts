import {
    declarerStage,
    type Auction,
    type Chair,
    type Declaring,
    type PassedIn,
    type Table,
} from "../routes/(start)/tables.ts";

export type Bubble = { kind: "bid" | "hold"; value: number };
// The declarer's mark slams in as `won` at the moment the auction ended and stays as `decl` after it.
export type DeclarerMark = "won" | "decl";
export type ChairMarks = {
    bubble: Bubble | null;
    passed: boolean;
    turn: boolean;
    waits: boolean;
    declarer: DeclarerMark | null;
};

// Every chair of a passed-in hand carries the pass mark, because everyone passed.
export const PASSED_IN_MARKS: ChairMarks = { bubble: null, passed: true, turn: false, waits: false, declarer: null };

const NO_MARKS: ChairMarks = { bubble: null, passed: false, turn: false, waits: false, declarer: null };

function bubbleOf(auction: Auction, seat: number): Bubble | null {
    const word = auction.words.find((spoken) => spoken.seat === seat);
    if (word?.action !== "bid" && word?.action !== "hold") return null;
    // The server names a value with every bid and every hold.
    return { kind: word.action, value: word.value as number };
}

// What a chair carries while the auction runs, as one viewer sees it; nothing before a deal or once it is over.
export function chairMarks(auction: Auction | undefined, seat: number, viewerSeat: number | undefined): ChairMarks {
    if (auction === undefined || auction.awaiting === null) return NO_MARKS;
    return {
        bubble: bubbleOf(auction, seat),
        passed: auction.words.some((word) => word.seat === seat && word.action === "pass"),
        turn: auction.turn_seat === seat,
        waits: auction.turn_seat === viewerSeat && auction.facing_seat === seat,
        declarer: null,
    };
}

// While the declarer decides, the declarer carries the mark and the turn for every viewer; at the moment the
// auction ended the other two carry the pass mark. Nothing once the game is declared.
export function decidingMarks(declaring: Declaring, seat: number, justWon: boolean): ChairMarks {
    if (declaring.stage === "declared") return NO_MARKS;
    const won = justWon && declaring.stage === "choosing";
    if (seat !== declaring.declarer_seat) return { ...NO_MARKS, passed: won };
    return { ...NO_MARKS, turn: true, declarer: won ? "won" : "decl" };
}

// The wait that the others see: the picked stage reads as the discarding, because to them it is the same wait.
export type DecidingPlaque = { kind: "won" | "choosing" | "discarding"; name: string; value: number };

// What the plaque says to an opponent or a watcher; the declarer's own view keeps the value alone.
export function decidingPlaque(table: Table, justWon: boolean): DecidingPlaque | null {
    const declaring = table.hand?.declaring;
    const value = table.hand?.auction.declared?.value;
    const name = table.chairs.find((chair) => chair.seat === declaring?.declarer_seat)?.occupant_name;
    if (!declaring || declaring.stage === "declared" || declarerStage(table) !== null) return null;
    if (value === undefined || !name) return null;
    if (declaring.stage === "choosing") return { kind: justWon ? "won" : "choosing", name, value };
    return { kind: "discarding", name, value };
}

// The name the plaque waits for: the player on turn while they are away.
export function awayOnTurn(auction: Auction, chairs: readonly Chair[]): string | null {
    const chair = chairs.find((one) => one.seat === auction.turn_seat && one.is_away);
    return chair?.occupant_name ?? null;
}

export type PassedInScene = { dealerSeat: number | null; dealerName: string | null };

// The next dealer shows only once the answer names one and nobody at the table is away.
export function passedInScene(passedIn: PassedIn | null, chairs: readonly Chair[]): PassedInScene | null {
    if (passedIn === null) return null;
    const dealer = chairs.find((chair) => chair.seat === passedIn.next_dealer_seat);
    if (dealer === undefined || chairs.some((chair) => chair.is_away)) return { dealerSeat: null, dealerName: null };
    return { dealerSeat: dealer.seat, dealerName: dealer.occupant_name };
}
