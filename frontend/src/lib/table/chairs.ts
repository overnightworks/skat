import { turnOf } from "#lib/cues.ts";
import { firstCardWait } from "#lib/kontra.ts";
import { words } from "#lib/words.ts";
import { drawingOrder, positionWord, type Chair, type Table } from "../../routes/(start)/tables.ts";
import type { ChairHand, ChairPlace, ChairScene, Sitter } from "./scene.ts";

// Where the chairs of the drawing order stand: the two others in playing order, then the viewer's own.
const PLACES: readonly ChairPlace[] = ["left", "right", "near"];

/**
 * The seat the table waits for, whatever the phase: the auction, the declaring, a Ramsch's pushing and the play. None
 * between hands, while the hand waits for a sitter and while the first card waits for a word.
 */
export function seatOnTurn(table: Table): number | null {
    return firstCardWait(table) !== null ? null : (turnOf(table)?.seat ?? null);
}

function sitterOf(chair: Chair): Sitter {
    if (chair.occupant_name === null) return { kind: "free" };
    return {
        kind: chair.occupant_kind === "agent" ? "agent" : "person",
        name: chair.occupant_name,
        away: chair.is_away,
    };
}

function handOf(chair: Chair, table: Table): ChairHand | null {
    if (chair.hand === null) return null;
    return {
        position: chair.hand.position,
        dealer: table.hand?.dealer_seat === chair.seat,
        cardsLeft: chair.hand.card_count,
    };
}

function whoOf(sitter: Sitter, mine: boolean): string {
    if (sitter.kind === "free") return words["table.seatFree"];
    return mine ? words["table.sideYou"] : sitter.name;
}

// The name leads with who sits there, then tells each further fact that holds, in the order a look draws them.
function nameOf(sitter: Sitter, who: string, hand: ChairHand | null, onTurn: boolean): string {
    if (sitter.kind === "free") return words["table.chairFree"];
    const facts = [
        who,
        sitter.kind === "agent" ? words["table.chairAgent"] : null,
        sitter.away ? words["table.seatAway"] : null,
        hand === null ? null : positionWord(hand.position),
        hand?.dealer === true ? words["table.dealer"] : null,
        hand === null ? null : words["table.chairCards"](hand.cardsLeft),
        onTurn ? words["table.chairOnTurn"] : null,
    ];
    return facts.filter((fact) => fact !== null).join(", ");
}

/** The table's three chairs, each with its place, its facts and the accessible name composed from them. */
export function chairScenes(table: Table): ChairScene[] {
    const turn = seatOnTurn(table);
    return drawingOrder(table.chairs).map((chair, index) => {
        const sitter = sitterOf(chair);
        const who = whoOf(sitter, chair.is_mine);
        const hand = handOf(chair, table);
        const onTurn = chair.seat === turn;
        return {
            seat: chair.seat,
            place: PLACES[index] as ChairPlace,
            sitter,
            who,
            mine: chair.is_mine,
            hand,
            onTurn,
            name: nameOf(sitter, who, hand, onTurn),
        };
    });
}
