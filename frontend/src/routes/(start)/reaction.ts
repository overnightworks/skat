import { REACTION_TOKENS, TABLE_REACTION_SUFFIX } from "#lib/wire.ts";
import type { Key, words } from "#lib/words.ts";
import { post, type Table } from "./tables.ts";

// The catalog keys whose word is a plain text, which a name or a glyph is.
type TextKey = { [Name in Key]: (typeof words)[Name] extends string ? Name : never }[Key];

// What a person throws at the table: an emote from the tray, or the tap on an object of the table.
export type Reaction = (typeof REACTION_TOKENS)[number];

// A reaction the table's answer carries for a few seconds; `number` counts them at the table, so a page plays each
// once. A watcher's has no seat and no name.
export type Thrown = { number: number; reaction: Reaction; by_seat: number | null; by_name: string | null };

// The catalog's name of each reaction, and the glyph an emote is drawn as; an object of the table is drawn by the table
// and has no glyph.
const REACTION_WORDS: Record<Reaction, { name: TextKey; mark: TextKey | null }> = {
    clap: { name: "table.reactionClap", mark: "table.reactionClapMark" },
    laugh: { name: "table.reactionLaugh", mark: "table.reactionLaughMark" },
    gasp: { name: "table.reactionGasp", mark: "table.reactionGaspMark" },
    fire: { name: "table.reactionFire", mark: "table.reactionFireMark" },
    cheers: { name: "table.reactionCheers", mark: "table.reactionCheersMark" },
    knock: { name: "table.reactionKnock", mark: "table.reactionKnockMark" },
    cocktail: { name: "table.objectCocktail", mark: null },
    shell: { name: "table.objectShell", mark: null },
    coaster: { name: "table.objectCoaster", mark: null },
    lamp: { name: "table.objectLamp", mark: null },
};

export function reactionName(reaction: Reaction): TextKey {
    return REACTION_WORDS[reaction].name;
}

/** The glyph of an emote; null for an object of the table. */
export function reactionMark(reaction: Reaction): TextKey | null {
    return REACTION_WORDS[reaction].mark;
}

/** Whether the reaction is a tap on an object of the table, which the table draws, and no emote that flies. */
export function isTableObject(reaction: Reaction): boolean {
    return REACTION_WORDS[reaction].mark === null;
}

/** The emotes of the tray, in the order the set lists them. */
export const EMOTES: readonly Reaction[] = REACTION_TOKENS.filter((reaction) => REACTION_WORDS[reaction].mark !== null);

/** The tray's element id, which its key names as the element it opens. */
export const REACTION_TRAY_ID = "reaction-tray";

// The reactions `table` carries that `previous` did not. A page with no table before it, as after a reload or a dropped
// connection, plays none: a reaction thrown before it arrived is over.
export function reactionsBetween(previous: Table | undefined, table: Table): Thrown[] {
    if (previous === undefined) return [];
    const seen = new Set(previous.reactions.map((thrown) => thrown.number));
    return table.reactions.filter((thrown) => !seen.has(thrown.number));
}

// A refused or failed throw changes nothing; the person sees no table change and throws again.
export function throwReaction(id: string, reaction: Reaction): Promise<unknown> {
    return post(id, TABLE_REACTION_SUFFIX, { reaction });
}
