import type { Component } from "svelte";
import type { Reaction, TableScene } from "#lib/table/scene.ts";
import type { TableIntents } from "#lib/table/intents.ts";
import type { Key } from "#lib/words.ts";

/** A piece of furniture a look draws on the felt: the object of the table it is, and the component that draws it. */
export interface Furnishing {
    readonly object: Reaction;
    readonly Piece: Component<{ taps: number; label: string; ontap: () => void }>;
}

/** The component set that draws a look's table from the scene, handing each gesture to the intents. */
export type Renderer = Component<{ look: LookEntry; scene: TableScene; intents: TableIntents }>;

/** One table style's look, which the registry finds by the style: its name, the renderer that draws it and the furniture that stands on its felt. */
export interface LookEntry {
    readonly name: Key;
    readonly renderer: Renderer;
    readonly furniture: readonly Furnishing[];
}
