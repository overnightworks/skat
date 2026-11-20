/**
 * A moment of the table as a closed form of time: seconds run from the moment's cue, a track says how one part looks at
 * an instant, and nothing reads a clock. So the same tracks draw a still of any instant and play the motion.
 */
export interface Timeline<Tracks> {
    /** From the cue to the instant every part has come to rest. */
    readonly seconds: number;
    readonly tracks: Tracks;
}

export type Track<Look> = (seconds: number) => Look;

/** Where a card-sized thing is drawn: its middle on the screen, its width, and the degrees it is turned. */
export interface Place {
    readonly x: number;
    readonly y: number;
    readonly width: number;
    readonly turn: number;
}

/**
 * How a moving part is drawn at one instant, measured from where the stylesheet rests it and in the frame it rests in:
 * pixels along its width and down its height, degrees, and shares of its size.
 */
export interface Pose {
    readonly x: number;
    readonly y: number;
    readonly turn: number;
    readonly wide: number;
    readonly tall: number;
    readonly opacity: number;
}

export const mix = (from: number, to: number, share: number): number => from + (to - from) * share;

/** How far the time has come through the `length` seconds that begin at `start`, from 0 to 1. */
export const phase = (seconds: number, start: number, length: number): number =>
    Math.min(1, Math.max(0, (seconds - start) / length));

/** A track's looks at evenly spaced instants no further apart than a frame, from the cue to the end, both included. */
export function sampled<Look>(track: Track<Look>, seconds: number, frameSeconds: number): Look[] {
    const frames = Math.ceil(seconds / frameSeconds);
    return Array.from({ length: frames + 1 }, (_, frame) => track((seconds * frame) / frames));
}
