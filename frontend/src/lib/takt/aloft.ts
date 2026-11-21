import type { Place, Pose } from "./timeline.ts";

/**
 * A card over the felt at one instant: the point of the felt below its middle on the screen, its height above that
 * point in card widths, the degrees it is turned, its size as a share of its resting size, how much of its face shows
 * (edge-on is 0, below it the back) and how much of it is seen.
 */
export interface Aloft {
    readonly x: number;
    readonly y: number;
    readonly up: number;
    readonly turn: number;
    readonly size: number;
    readonly facing: number;
    readonly shown: number;
}

// Per card width of height the shade grows this much wider and this much paler.
const SHADE_WIDENS = 0.3;
const SHADE_PALES = 0.6;
// Edge-on, a card keeps this share of its width.
const EDGE_ON = 0.04;

/**
 * The card and its shade as the page draws them in the frame the card rests in: the card stands above its point of the
 * felt, the shade lies on it, and the screen's pixels become those of the resting frame.
 */
export function drawnFrom(rests: Place, aloft: Aloft): { readonly card: Pose; readonly shade: Pose } {
    const frame = (rests.turn * Math.PI) / 180;
    const piece = (height: number, widens: number, pales: number): Pose => {
        const [x, y] = [aloft.x - rests.x, aloft.y - height * aloft.up * rests.width - rests.y];
        const spread = aloft.size * (1 + widens * aloft.up);
        return {
            x: x * Math.cos(frame) + y * Math.sin(frame),
            y: y * Math.cos(frame) - x * Math.sin(frame),
            turn: aloft.turn - rests.turn,
            wide: spread * Math.max(EDGE_ON, Math.abs(aloft.facing)),
            tall: spread,
            opacity: aloft.shown / (1 + pales * aloft.up),
        };
    };
    return { card: piece(1, 0, 0), shade: piece(0, SHADE_WIDENS, SHADE_PALES) };
}
