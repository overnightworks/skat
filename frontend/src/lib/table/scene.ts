import { reactionName, type Reaction } from "../../routes/(start)/reaction.ts";
import { words } from "../words.ts";

// A look reads the table through this contract and never the routes or the wire, so the names it needs pass through here.
export type { Reaction } from "../../routes/(start)/reaction.ts";
export type { TableStyle } from "../../routes/(start)/tables.ts";

/** What lies on the table for a look to draw: how often each object of the table was tapped at this table. */
export interface TableScene {
    readonly taps: Readonly<Partial<Record<Reaction, number>>>;
}

/**
 * Which move an object makes after this many taps: the two moves alternate, so a CSS animation that names one of them
 * starts anew at every tap without the button being made again. None before the first tap.
 */
export function beatAfter(taps: number): "odd" | "even" | undefined {
    if (taps === 0) return undefined;
    return taps % 2 === 1 ? "odd" : "even";
}

/** What an object of the table is called, as its accessible name and as the table announces it. */
export function objectName(object: Reaction): string {
    return words[reactionName(object)];
}
