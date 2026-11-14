import type { MarkedPart } from "overnightworks-design";
import { listFormat, words } from "#lib/words.ts";
import type { Chair, Kontra, Table, Word } from "../routes/(start)/tables.ts";

export type SaidWord = Kontra["said"][number];
// The callout the table shows when a word is said: the word with its mark, the sayer's face and what a screen reader says.
export type Stamp = { text: string; label: string; initial: string; agent: boolean };

export function wordLabel(word: Word): string {
    return words[`kontra.${word}`];
}

// The word the viewer's own chair may say now; the server decides who may say what, the page only shows it.
export function keyWord(table: Table): Word | null {
    return table.hand?.playing?.kontra?.my_word ?? null;
}

// The word the viewer's chair may give up before the first card: the one it owes while that card waits on it.
export function declinableWord(table: Table): Word | null {
    const wait = firstCardWait(table);
    return table.chairs.some((chair) => chair.is_mine && wait?.owes(chair.seat)) ? keyWord(table) : null;
}

export function stampOf(table: Table, said: SaidWord): Stamp {
    // A word is said by a seat of the table, which keeps its chair when its occupant leaves.
    const chair = table.chairs.find((each) => each.seat === said.seat) as Chair;
    const name = chair.occupant_name ?? "";
    const word = wordLabel(said.word);
    return {
        text: words["kontra.stamp"]({ word }),
        label: words["kontra.saidBy"]({ name, word }),
        initial: name.slice(0, 1),
        agent: chair.occupant_kind === "agent",
    };
}

// The plaque carries the last word with the factor the words make, until the hand ends.
export function plaqueLine(kontra: Kontra | null): readonly MarkedPart<"factor">[] | null {
    if (kontra === null || kontra.said.length === 0) return null;
    const last = kontra.said.at(-1) as SaidWord;
    return words["kontra.plaque"]({ word: wordLabel(last.word), factor: String(kontra.factor) });
}

// What a table whose Kontra words end with the first card shows while that card waits: the chairs it waits on glow, one
// line names them, the seats that said no carry a cross, and the leader's cards stay dimmed until the wait ends.
export type FirstCardWait = {
    // Whether the first card waits on the seat for a word.
    owes: (seat: number) => boolean;
    marks: ReadonlyMap<number, "declined">;
    // Whether the seat leads and so holds its cards back.
    held: (seat: number | undefined) => boolean;
    initials: readonly string[];
    text: string;
};

export function firstCardWait(table: Table): FirstCardWait | null {
    const playing = table.hand?.playing;
    const kontra = playing?.kontra;
    if (!kontra || kontra.first_card_waits_on.length === 0) return null;
    // A seat the first card waits on belongs to a chair with a sitter: no seat is awaited while a chair is open.
    const chairs = kontra.first_card_waits_on.map((seat) => table.chairs.find((each) => each.seat === seat) as Chair);
    const names = chairs.map((chair) => (chair.is_mine ? words["kontra.you"] : (chair.occupant_name as string)));
    return {
        owes: (seat) => kontra.first_card_waits_on.includes(seat),
        marks: new Map(kontra.first_card_declined.map((seat) => [seat, "declined"])),
        held: (seat) => seat !== undefined && seat === playing?.turn_seat,
        initials: chairs.map((chair) => (chair.occupant_name as string).slice(0, 1)),
        text: words["kontra.firstCardWaits"]({ names: listFormat.format(names) }),
    };
}
