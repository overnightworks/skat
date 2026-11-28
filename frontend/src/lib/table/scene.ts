import { reactionName, type Reaction } from "../../routes/(start)/reaction.ts";
import type { Position, Table } from "../../routes/(start)/tables.ts";
import { words } from "../words.ts";
import { chairScenes } from "./chairs.ts";

// A look reads the table through this contract and never the routes or the wire, so the names it needs pass through here.
export type { Reaction } from "../../routes/(start)/reaction.ts";
export type { Position, TableStyle } from "../../routes/(start)/tables.ts";
export { positionWord } from "../../routes/(start)/tables.ts";

/** What lies on the table for a look to draw: how often each object of the table was tapped at this table. */
export interface TableScene {
    readonly taps: Readonly<Partial<Record<Reaction, number>>>;
}

/** Who sits on a chair: nobody, or a person or an agent under the name the table knows. */
export type Sitter =
    { readonly kind: "free" } | { readonly kind: "person" | "agent"; readonly name: string; readonly away: boolean };

/** What a chair holds of the running hand. */
export interface ChairHand {
    readonly position: Position;
    readonly dealer: boolean;
    readonly cardsLeft: number;
}

/** Where a chair stands as the viewer sees the table: the viewer's own is near, a watcher's third chair too. */
export type ChairPlace = "left" | "right" | "near";

/** One chair of the table. A look draws it as a group that carries `name`, so every look tells a chair the same way. */
export interface ChairScene {
    readonly seat: number;
    readonly place: ChairPlace;
    readonly sitter: Sitter;
    /** The word a look draws for who sits there: the sitter's name, the viewer's own word or the free chair's. */
    readonly who: string;
    /** The viewer's own chair. */
    readonly mine: boolean;
    /** None between hands. */
    readonly hand: ChairHand | null;
    readonly onTurn: boolean;
    /** The chair's accessible name, which tells every fact above. */
    readonly name: string;
}

/** The whole table for a look that draws the whole surface. Its root is the page's main landmark and carries `name`. */
export interface SurfaceScene extends TableScene {
    readonly name: string;
    /** The three chairs, the viewer's own last. */
    readonly chairs: readonly ChairScene[];
    /** The sentence about who has just taken or left a chair, while it stands. */
    readonly notice: string | null;
}

/** The scene of a running table as the page shows it. */
export function surfaceScene(table: Table, taps: TableScene["taps"], notice: string | null): SurfaceScene {
    return { name: words["table.landmark"], chairs: chairScenes(table), taps, notice };
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
