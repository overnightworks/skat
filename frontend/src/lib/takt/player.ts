import { sampled, type Place, type Pose, type Track } from "./timeline.ts";

const FRAME_SECONDS = 1 / 60;
const DEGREES_PER_RADIAN = 180 / Math.PI;
// A computed transform reads `none` or a matrix whose first two numbers are the cosine and the sine of its turn.
const MATRIX_START = /^matrix(?:3d)?\(([^,]+),([^,]+)/;

type Part = Pick<Animatable, "animate">;

function turnOf(transform: string): number {
    const matrix = MATRIX_START.exec(transform);
    return matrix === null ? 0 : Math.atan2(Number(matrix[2]), Number(matrix[1])) * DEGREES_PER_RADIAN;
}

/** Where an element is drawn: the middle of its box, its laid-out width and the turn it and the elements around it carry. */
export function placeOf(element: Element): Place {
    const box = element.getBoundingClientRect();
    let turn = 0;
    for (let each: Element | null = element; each !== null; each = each.parentElement)
        turn += turnOf(getComputedStyle(each).transform);
    return {
        x: box.left + box.width / 2,
        y: box.top + box.height / 2,
        width: Number.parseFloat(getComputedStyle(element).width),
        turn,
    };
}

/** How a part is played: whether it `stays` as its track ends, and whether one of its pseudo-elements is meant. */
export interface Playing {
    /** The part stays as its track ends until it is let rest or taken away; without it, it rests where the stylesheet puts it. */
    readonly stays?: boolean;
    readonly pseudoElement?: "::after";
}

/** Ends what still plays on an element and on everything in it, so each part rests where the stylesheet puts it. */
export function letRest(element: Pick<Element, "getAnimations">): void {
    for (const played of element.getAnimations({ subtree: true })) played.cancel();
}

function play(part: Part, frames: Keyframe[], seconds: number, { stays = false, pseudoElement }: Playing): void {
    part.animate(frames, { duration: seconds * 1000, fill: stays ? "forwards" : "none", pseudoElement });
}

// The player writes transform and opacity alone, so the browser composes a moment without laying out or painting again.

/** Moves a part along its track for `seconds`. */
export function move(part: Part, track: Track<Pose>, seconds: number, playing: Playing = {}): void {
    const frames = sampled(track, seconds, FRAME_SECONDS).map(({ x, y, turn, wide, tall, opacity }) => ({
        transform: `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) rotate(${turn.toFixed(1)}deg) scale(${wide.toFixed(3)}, ${tall.toFixed(3)})`,
        opacity,
    }));
    play(part, frames, seconds, playing);
}

/** Lets a part appear or fade along its track for `seconds`, wherever the stylesheet draws it. */
export function fade(part: Part, track: Track<number>, seconds: number, playing: Playing = {}): void {
    play(
        part,
        sampled(track, seconds, FRAME_SECONDS).map((opacity) => ({ opacity })),
        seconds,
        playing,
    );
}
