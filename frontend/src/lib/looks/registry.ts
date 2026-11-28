import type { TableStyle } from "#lib/table/scene.ts";
import klassik from "./klassik/entry.ts";
import lampe from "./lampe/entry.ts";
import type { LookEntry, SurfaceLook } from "./look.ts";
import strandbar from "./strandbar/entry.ts";

const LOOKS: Record<TableStyle, LookEntry> = { klassik, strandbar };

/** The look a table of this style is drawn in. */
export function lookOf(style: TableStyle): LookEntry {
    return LOOKS[style];
}

/** The look under construction, which a device shows in place of today's surface once its person turned it on. */
export const lookUnderConstruction: SurfaceLook = lampe;
