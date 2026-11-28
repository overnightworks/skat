import type { TableStyle } from "#lib/table/scene.ts";
import klassik from "./klassik/entry.ts";
import type { LookEntry } from "./look.ts";
import strandbar from "./strandbar/entry.ts";

const LOOKS: Record<TableStyle, LookEntry> = { klassik, strandbar };

/** The look a table of this style is drawn in. */
export function lookOf(style: TableStyle): LookEntry {
    return LOOKS[style];
}
