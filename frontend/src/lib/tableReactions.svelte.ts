import { MOTION_SETS } from "./motionSets.ts";
import { motionInForce } from "./settings.svelte.ts";
import { soundForReaction } from "./tableSound.ts";
import { isTableObject, type Reaction, type Thrown } from "../routes/(start)/reaction.ts";

const MILLISECONDS_PER_SECOND = 1000;
/** Where motion is not welcome an emote stands still on the felt this long. */
const STILL_EMOTE_SECONDS = 2.5;

// The emotes that fly or lie on the felt now, and how often each object of the table was tapped at this table.
let flying = $state<Thrown[]>([]);
let taps = $state<Partial<Record<Reaction, number>>>({});
let timers: ReturnType<typeof setTimeout>[] = [];

export function flyingEmotes(): readonly Thrown[] {
    return flying;
}

/**
 * Which move an object makes next: the two moves alternate, so a CSS animation that names one of them starts anew at every
 * tap without the button being made again. None until the first tap.
 */
export function beatOf(object: Reaction): "odd" | "even" | undefined {
    const count = taps[object] ?? 0;
    if (count === 0) return undefined;
    return count % 2 === 1 ? "odd" : "even";
}

function stayOf(): number {
    const id = motionInForce();
    if (id === undefined) return STILL_EMOTE_SECONDS;
    const { emoteLandsSeconds, emoteRestsSeconds } = MOTION_SETS[id];
    return emoteLandsSeconds + emoteRestsSeconds;
}

function show(thrown: Thrown): void {
    flying = [...flying, thrown];
    const timer = setTimeout(() => {
        timers = timers.filter((each) => each !== timer);
        flying = flying.filter((each) => each.number !== thrown.number);
    }, stayOf() * MILLISECONDS_PER_SECOND);
    timers.push(timer);
}

/** Plays what the table's update brought: every reaction sounds, an emote flies and an object makes its move. */
export function receiveReactions(brought: readonly Thrown[]): void {
    for (const thrown of brought) {
        soundForReaction(thrown.reaction);
        if (isTableObject(thrown.reaction)) taps[thrown.reaction] = (taps[thrown.reaction] ?? 0) + 1;
        else show(thrown);
    }
}

/** Forgets what flies, as the page leaves one table for another. */
export function resetReactions(): void {
    for (const timer of timers) clearTimeout(timer);
    timers = [];
    flying = [];
    taps = {};
}
