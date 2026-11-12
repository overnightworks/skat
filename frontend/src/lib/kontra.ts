import { words } from "#lib/words.ts";
import type { Chair, Kontra, Table, Word } from "../routes/(start)/tables.ts";

export type SaidWord = Kontra["said"][number];
// The callout the table shows when a word is said: the word with its mark, the sayer's face and what a screen reader says.
export type Stamp = { text: string; label: string; initial: string; agent: boolean };
export type PlaqueLine = { word: string; factor: string };

export function wordLabel(word: Word): string {
    return words[`kontra.${word}`];
}

// The word the viewer's own chair may say now; the server decides who may say what, the page only shows it.
export function keyWord(table: Table): Word | null {
    return table.hand?.playing?.kontra?.my_word ?? null;
}

// The word the update from `previous` to `next` brought, the last when it brought several. A page that has no table
// before it, as after a reload or a dropped connection, stamps nothing: the plaque already tells the word.
export function wordSaidBetween(previous: Table | undefined, next: Table): SaidWord | null {
    if (previous === undefined || next.version <= previous.version) return null;
    const before = previous.hand?.playing?.kontra?.said ?? [];
    const after = next.hand?.playing?.kontra?.said ?? [];
    return after.length > before.length ? (after[after.length - 1] as SaidWord) : null;
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
export function plaqueLine(kontra: Kontra | null): PlaqueLine | null {
    if (kontra === null || kontra.said.length === 0) return null;
    const last = kontra.said[kontra.said.length - 1] as SaidWord;
    return { word: wordLabel(last.word), factor: `×${String(kontra.factor)}` };
}
