/** A rectangle in the viewport's pixels, as `getBoundingClientRect` gives it. */
export interface Box {
    readonly left: number;
    readonly top: number;
    readonly width: number;
    readonly height: number;
}

export interface Viewport {
    readonly width: number;
    readonly height: number;
}

export type PanelSide = "below" | "above";

/** Every number is in pixels; `edge` is counted from the viewport's top for a panel below its button and from its bottom for one above. */
export interface PanelPlace {
    readonly width: number;
    readonly left: number;
    /** From the panel's left edge to the middle of its caret. */
    readonly caret: number;
    readonly edge: number;
    /** The tallest the panel may be. */
    readonly room: number;
}

export const EDGE_MARGIN = 16;
/** The caret and its breathing space between the button and the panel. */
const GAP = 12;
/** The caret keeps this far from a panel's corner, which is rounded. */
const CARET_INSET = 18;
const TALLEST_SHARE = 0.7;

const clamp = (value: number, lowest: number, highest: number): number => Math.min(Math.max(value, lowest), highest);

/** Where a panel of the wanted width hangs on its button: inside the edge margin, its caret over the button. */
export function placePanel(anchor: Box, view: Viewport, wanted: number, side: PanelSide): PanelPlace {
    const width = Math.min(wanted, view.width - 2 * EDGE_MARGIN);
    const middle = anchor.left + anchor.width / 2;
    const left = clamp(middle - width / 2, EDGE_MARGIN, view.width - EDGE_MARGIN - width);
    const edge = side === "below" ? anchor.top + anchor.height + GAP : view.height - anchor.top + GAP;
    const roomToTheMargin = side === "below" ? view.height - edge - EDGE_MARGIN : anchor.top - GAP - EDGE_MARGIN;
    return {
        width,
        left,
        caret: clamp(middle - left, CARET_INSET, width - CARET_INSET),
        edge,
        room: Math.max(0, Math.min(roomToTheMargin, TALLEST_SHARE * view.height)),
    };
}

/** The content security policy admits no inline style, so the place goes in as custom properties the stylesheet reads. */
export function applyPanelPlace(panel: { readonly style: Pick<CSSStyleDeclaration, "setProperty"> }, place: PanelPlace): void {
    panel.style.setProperty("--panel-width", `${String(place.width)}px`);
    panel.style.setProperty("--panel-left", `${String(place.left)}px`);
    panel.style.setProperty("--panel-caret", `${String(place.caret)}px`);
    panel.style.setProperty("--panel-edge", `${String(place.edge)}px`);
    panel.style.setProperty("--panel-room", `${String(place.room)}px`);
}
