import type { Thrown } from "./reaction.ts";
import { drawingOrder, type Chair } from "./tables.ts";

// Where an emote starts and where it lands, in percent of the felt: the first chair stands at the far left, the second at
// the far right, the own chair at the near edge, and a watcher throws from beyond it. The stylesheet flies the emote
// between the two points; the dashed trail is drawn along the same arc. A knock has one point, beside the chair.
export type Point = { x: number; y: number };

/** Where an emote of the felt starts and lands, the arc it flies as a path, and whether it is a knock, which does not fly. */
export type Flight = { origin: Point; landing: Point; knocked: boolean; trail: string | null };

const CHAIR_ORIGINS: readonly Point[] = [
    { x: 8, y: 2 },
    { x: 92, y: 2 },
    { x: 50, y: 96 },
];
const RIM_ORIGIN: Point = { x: 50, y: 112 };
const KNOCK_SPOTS: readonly Point[] = [
    { x: 20, y: 30 },
    { x: 80, y: 30 },
    { x: 50, y: 80 },
];
const RIM_KNOCK_SPOT: Point = { x: 12, y: 86 };
const SPOTS: readonly Point[] = [
    { x: 42, y: 50 },
    { x: 58, y: 54 },
    { x: 50, y: 42 },
    { x: 36, y: 58 },
    { x: 64, y: 44 },
];
// The arc rises this far above the higher of its two ends, and its last stretch is what the trail shows.
const ARC_LIFT = 8;
const TRAIL_FROM = 0.72;
const TRAIL_STEP = 0.04;
const TRAIL_POINTS = 8;

function curve(t: number, from: number, control: number, to: number): number {
    return (1 - t) ** 2 * from + 2 * (1 - t) * t * control + t ** 2 * to;
}

function trailOf(origin: Point, landing: Point): string {
    const control = { x: landing.x + (origin.x - landing.x) * 0.45, y: Math.min(landing.y, origin.y) - ARC_LIFT };
    return Array.from({ length: TRAIL_POINTS }, (_, index) => {
        const t = TRAIL_FROM + index * TRAIL_STEP;
        const point = `${curve(t, origin.x, control.x, landing.x).toFixed(1)} ${curve(t, origin.y, control.y, landing.y).toFixed(1)}`;
        return `${index === 0 ? "M" : "L"}${point}`;
    }).join("");
}

/** The flight of a reaction thrown at a table with these chairs: from the thrower's chair, or from the rim for a watcher. */
export function flightOf(thrown: Thrown, chairs: Chair[]): Flight {
    const place = drawingOrder(chairs).findIndex((chair) => chair.seat === thrown.by_seat);
    const knocked = thrown.reaction === "knock";
    const landing = knocked ? (KNOCK_SPOTS[place] ?? RIM_KNOCK_SPOT) : (SPOTS[thrown.number % SPOTS.length] as Point);
    const origin = knocked ? landing : (CHAIR_ORIGINS[place] ?? RIM_ORIGIN);
    return { origin, landing, knocked, trail: knocked ? null : trailOf(origin, landing) };
}
