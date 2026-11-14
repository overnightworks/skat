import { inDisplayOrder } from "#lib/handOrder.ts";
import type { SideNames } from "#lib/playView.ts";
import { listFormat, words } from "#lib/words.ts";
import type { Card, CardState, GameEnding, GameSheet, Sides } from "../routes/(start)/tables.ts";

const TRICKS_IN_A_GAME = 10;

export type SheetSeat = { seat: number; name: string; initial: string };
export type SheetHand = { seat: SheetSeat; cards: { card: Card; state: CardState }[] };
export type SheetTrick = {
    number: number;
    // From the lead on, each with the seat that played it.
    cards: { card: Card; by: SheetSeat }[];
    taker: SheetSeat | null;
    // The card points of a trick that was taken; an interrupted trick has none.
    points: string | null;
    // Whose colour the trick stands in: the declarer's tricks stand apart from the opponents'.
    side: "declarer" | "opponents" | "none";
};
export type SheetEnd = { label: string; by: SheetSeat | null };
export type SheetCount =
    | { kind: "declared"; sides: SideNames; points: Sides }
    | { kind: "ramsch"; seats: { seat: SheetSeat; points: number; most: boolean }[] };
export type SheetCards = {
    skat: Card[];
    // A Ramsch's skat counted for these seats.
    skatTakers: SheetSeat[];
    putAway: { by: SheetSeat; cards: Card[] }[];
    hands: SheetHand[];
    tricks: SheetTrick[];
};
export type GameSheetView = { count: SheetCount; cards: SheetCards | null; end: SheetEnd | null };

const ENDING_WORDS: Partial<Record<GameEnding, string>> = {
    "given-up": words["result.givenUp"],
    "thrown-down": words["table.sheetThrownDown"],
    shortened: words["table.sheetShortened"],
    "played-open": words["table.sheetPlayedOpen"],
};

function cardKey(card: Card): string {
    return `${card.suit}-${card.rank}`;
}

// The page draws what the server sent: each seat as the game named it, each trick by the server's taker and points.
export function gameSheetView(sheet: GameSheet): GameSheetView {
    const seats = [1, 2, 3].map((seat): SheetSeat => {
        const name = sheet.seat_names[seat - 1] ?? words["table.seriesNameless"];
        return { seat, name, initial: name.slice(0, 1) };
    });
    const seatOf = (seat: number): SheetSeat => seats[seat - 1] as SheetSeat;
    const cards = sheet.cards;
    const played = cards?.tricks.length ?? 0;
    const count = sheet.count;
    if (count.kind === "ramsch") {
        const most = Math.max(...count.seat_points);
        return {
            count: {
                kind: "ramsch",
                seats: seats.map((seat) => ({
                    seat,
                    points: count.seat_points[seat.seat - 1] as number,
                    most: count.seat_points[seat.seat - 1] === most,
                })),
            },
            cards: cards === null ? null : cardsView(cards, seatOf, null),
            end:
                count.durchmarsch_seat === null
                    ? null
                    : { label: words["table.sheetDurchmarsch"], by: seatOf(count.durchmarsch_seat) },
        };
    }
    const opponents = seats.filter((seat) => seat.seat !== count.declarer_seat).map((seat) => seat.name);
    const ending = ENDING_WORDS[count.ending] ?? (played < TRICKS_IN_A_GAME ? words["table.sheetDecided"] : null);
    return {
        count: {
            kind: "declared",
            sides: { declarer: seatOf(count.declarer_seat).name, opponents: listFormat.format(opponents) },
            points: { declarer: count.declarer_points, opponents: count.opponents_points },
        },
        cards: cards === null ? null : cardsView(cards, seatOf, count.declarer_seat),
        end:
            cards === null || ending === null
                ? null
                : { label: ending, by: count.ended_by_seat === null ? null : seatOf(count.ended_by_seat) },
    };
}

function sideOf(takerSeat: number | null, declarerSeat: number | null): SheetTrick["side"] {
    if (takerSeat === null || declarerSeat === null) {
        return "none";
    }
    return takerSeat === declarerSeat ? "declarer" : "opponents";
}

function cardsView(
    cards: NonNullable<GameSheet["cards"]>,
    seatOf: (seat: number) => SheetSeat,
    declarerSeat: number | null,
): SheetCards {
    const putBy = [...new Set(cards.put_away.map((put) => put.seat))];
    return {
        skat: cards.skat,
        skatTakers: cards.skat_takers.map(seatOf),
        putAway: putBy.map((seat) => ({
            by: seatOf(seat),
            cards: cards.put_away.filter((put) => put.seat === seat).map((put) => put.card),
        })),
        hands: cards.hands.map((hand) => {
            const states = new Map(hand.cards.map((each) => [cardKey(each.card), each.state]));
            return {
                seat: seatOf(hand.seat),
                cards: inDisplayOrder(hand.cards.map((each) => each.card)).map((card) => ({
                    card,
                    state: states.get(cardKey(card)) as CardState,
                })),
            };
        }),
        tricks: cards.tricks.map((trick) => ({
            number: trick.number,
            cards: trick.cards.map((each) => ({ card: each.card, by: seatOf(each.seat) })),
            taker: trick.taker_seat === null ? null : seatOf(trick.taker_seat),
            points: trick.points === null ? null : String(trick.points),
            side: sideOf(trick.taker_seat, declarerSeat),
        })),
    };
}
