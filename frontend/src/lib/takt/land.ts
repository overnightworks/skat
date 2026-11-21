import type { Card } from "../../routes/(start)/tables.ts";
import { drawnFrom, type Aloft } from "./aloft.ts";
import { cardFork } from "./seed.ts";
import { mix, phase, type Place, type Pose, type Timeline, type Track } from "./timeline.ts";

/** How a motion set throws a card. */
export interface LandSet {
    /** From the cue to the instant the card touches the felt. */
    readonly flightSeconds: number;
    /** How high the arc rises, in card widths. */
    readonly lift: number;
    /** How much the card grows at the top of its arc. */
    readonly swell: number;
    /** The least and the most degrees a toss turns the card past its lie; the slide takes them back. */
    readonly spin: readonly [number, number];
    /** How fast the felt stops the sliding card, per second. */
    readonly grip: number;
    /** How much the flight slows toward the felt: 0 flies evenly, 1 slows all the way. */
    readonly ease: number;
    /** How much the card gives way as it hits. */
    readonly squash: number;
    /** Whether a card out of a hidden hand flies face down and turns over on its way. */
    readonly flips: boolean;
}

/** How far a card rests off its slot, in card widths, and how far it is turned off it, in degrees. */
export interface Lie {
    readonly x: number;
    readonly y: number;
    readonly turn: number;
}

/** One throw, between two places the page measured. */
export interface Flight {
    /** Where the card leaves from; nothing for a card whose hand the page does not draw. */
    readonly from: Place | undefined;
    /** Where the stylesheet rests the card. */
    readonly to: Place;
    /** Whether the card leaves a hand that hides its faces. */
    readonly faceDown: boolean;
    /** The degrees the toss turns the card past its lie. */
    readonly carry: number;
}

export interface LandTracks {
    readonly card: Track<Pose>;
    /** The card's shade, which stays on the felt below it. */
    readonly shade: Track<Pose>;
    /** How much of the card's back shows. */
    readonly rear: Track<number>;
    /** How much of the player's name shows. */
    readonly name: Track<number>;
}

export type LandTimeline = Timeline<LandTracks>;

// A card lies off its slot sideways and upward, never downward: below every card hangs its name, and below the near
// card the own seat begins. The lie belongs to no motion set, so devices with different sets show the same trick.
const LIE_REACH = 0.12;
const LIE_TURN_DEGREES = 10;
// The felt's grip alone never ends a slide, so it ends where a hundredth of it would be left.
const SLIDE_LEFT_AT_REST = 0.01;
const SQUASH_FADES_PER_SECOND = 22;
// A card turns over within this part of its flight.
const FLIP_STARTS = 0.1;
const FLIP_LASTS = 0.5;
// A card out of a hidden hand that does not turn over fades in over this share of its flight.
const FADES_IN = 0.4;
// A name never flies: it appears below its card, this long after the card touched the felt.
const NAME_WAITS_SECONDS = 0.04;
const NAME_APPEARS_SECONDS = 0.14;

/** The lie of a card in a game: the same for every seat and watcher, in whichever slot each of them sees the card. */
export function lieOf(seed: string, card: Card): Lie {
    const lie = cardFork(seed, card, "lie");
    return {
        x: lie.between(-LIE_REACH, LIE_REACH),
        y: lie.between(-LIE_REACH, 0),
        turn: lie.between(-LIE_TURN_DEGREES, LIE_TURN_DEGREES),
    };
}

/** The degrees a card's toss turns it past its lie in a set, to either side. */
export function carryOf(seed: string, card: Card, land: LandSet): number {
    const toss = cardFork(seed, card, "toss");
    return mix(land.spin[0], land.spin[1], toss.between(0, 1)) * toss.sign();
}

/** What a throw needs of a set: a trick thrown onto its pile flies and slides as a card thrown onto the felt does. */
export type Throw = Pick<LandSet, "flightSeconds" | "lift" | "swell" | "grip" | "ease" | "squash">;

/** How fast the felt has to stop a slide for it to end within `seconds`, per second. */
export const gripStoppingWithin = (seconds: number): number => -Math.log(SLIDE_LEFT_AT_REST) / seconds;

/**
 * The instants of a landing that need no measure: the card touches the felt when its flight ends, and sounds then, and
 * it lies when its slide has ended.
 */
export function landInstants(land: Throw): Readonly<Record<"impact" | "lies", number>> {
    return { impact: land.flightSeconds, lies: land.flightSeconds - Math.log(SLIDE_LEFT_AT_REST) / land.grip };
}

/**
 * A thrown card flies an arc while it turns, lands short of its place and slides the rest against the felt, its turn
 * dying with the slide. `ahead` is the share of the way still to go, `up` the height in card widths.
 */
export function thrownAt(land: Throw, start: { turn: number; size: number }, carry: number, seconds: number) {
    const flown = phase(seconds, 0, land.flightSeconds);
    const after = seconds - land.flightSeconds;
    // The slide starts as fast as the flight ends, so the flight covers this share of the way.
    const share = 1 / (1 + (1 - land.ease) / (land.flightSeconds * land.grip));
    if (after <= 0) {
        const air = 4 * flown * (1 - flown);
        return {
            ahead: 1 - mix(flown, 1 - (1 - flown) ** 2, land.ease) * share,
            up: land.lift * air,
            turn: mix(start.turn, -carry, flown),
            size: mix(start.size, 1, flown) * (1 + land.swell * air),
        };
    }
    const sliding = Math.max(0, (Math.exp(-land.grip * after) - SLIDE_LEFT_AT_REST) / (1 - SLIDE_LEFT_AT_REST));
    return {
        ahead: (1 - share) * sliding,
        up: 0,
        turn: -carry * sliding,
        size: 1 - land.squash * Math.exp(-SQUASH_FADES_PER_SECOND * after),
    };
}

/**
 * The landing of one card: it flies from `from` to `to`, its shade stays on the felt, and its name appears once it
 * lies. A card without a place to leave from has no landing and lies at once.
 */
export function landTimeline(land: LandSet, { from, to, faceDown, carry }: Flight): LandTimeline | undefined {
    if (from === undefined) return undefined;
    const flips = faceDown && land.flips;
    const fadesIn = faceDown && !land.flips;
    // A card that fades in starts as it will lie; any other starts as it stood in its hand, turning the shorter way.
    const start = { turn: fadesIn ? 0 : ((from.turn - to.turn + 540) % 360) - 180, size: from.width / to.width };
    const away = { x: from.x - to.x, y: from.y - to.y };
    const facing = (seconds: number): number =>
        flips
            ? -Math.cos(Math.PI * phase(seconds, land.flightSeconds * FLIP_STARTS, land.flightSeconds * FLIP_LASTS))
            : 1;
    const shown = (seconds: number): number => (fadesIn ? phase(seconds, 0, land.flightSeconds * FADES_IN) : 1);
    const aloft = (seconds: number): Aloft => {
        const { ahead, up, turn, size } = thrownAt(land, start, carry, seconds);
        return {
            x: to.x + away.x * ahead,
            y: to.y + away.y * ahead,
            up,
            turn: to.turn + turn,
            size,
            facing: facing(seconds),
            shown: shown(seconds),
        };
    };
    return {
        seconds: landInstants(land).lies,
        tracks: {
            card: (seconds) => drawnFrom(to, aloft(seconds)).card,
            shade: (seconds) => drawnFrom(to, aloft(seconds)).shade,
            rear: (seconds) => (flips && facing(seconds) <= 0 ? 1 : 0),
            name: (seconds) => phase(seconds, land.flightSeconds + NAME_WAITS_SECONDS, NAME_APPEARS_SECONDS),
        },
    };
}
