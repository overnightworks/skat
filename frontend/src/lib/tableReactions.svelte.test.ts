import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Thrown } from "../routes/(start)/reaction.ts";

const sounded = vi.hoisted(() => [] as string[]);
vi.mock("./tableSound.ts", () => ({
    soundForReaction: (reaction: string) => sounded.push(reaction),
}));
vi.mock("./settings.svelte.ts", () => ({ motionInForce: () => motion }));
let motion: "dezent" | "verspielt" | undefined;

const { beatOf, flyingEmotes, receiveReactions, resetReactions } = await import("./tableReactions.svelte.ts");
const { MOTION_SETS } = await import("./motionSets.ts");

const MILLISECONDS_PER_SECOND = 1000;
const thrown = (number: number, reaction: Thrown["reaction"]): Thrown => ({
    number,
    reaction,
    by_seat: 1,
    by_name: "Anna",
});

describe("what the table plays of the reactions it receives", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        motion = "verspielt";
        sounded.length = 0;
    });

    afterEach(() => {
        resetReactions();
        vi.useRealTimers();
    });

    it("sounds every reaction and lets an emote fly until its motion set has let it rest", () => {
        receiveReactions([thrown(1, "fire"), thrown(2, "lamp")]);
        const stay = MOTION_SETS.verspielt.emoteLandsSeconds + MOTION_SETS.verspielt.emoteRestsSeconds;

        const flyingNow = flyingEmotes().map((each) => each.reaction);
        vi.advanceTimersByTime(stay * MILLISECONDS_PER_SECOND);

        expect([sounded, flyingNow, flyingEmotes()]).toEqual([["fire", "lamp"], ["fire"], []]);
    });

    it("lets an emote lie still for a while where motion is not welcome", () => {
        motion = undefined;

        receiveReactions([thrown(1, "clap")]);
        vi.advanceTimersByTime(MILLISECONDS_PER_SECOND);
        const lying = flyingEmotes().length;
        vi.advanceTimersByTime(3 * MILLISECONDS_PER_SECOND);

        expect([lying, flyingEmotes().length]).toEqual([1, 0]);
    });

    it("moves an object on every tap, its two beats taking turns so that each tap starts the move anew", () => {
        const beats = [beatOf("cocktail")];
        for (const number of [1, 2, 3]) {
            receiveReactions([thrown(number, "cocktail")]);
            beats.push(beatOf("cocktail"));
        }

        expect([beats, beatOf("shell"), flyingEmotes()]).toEqual([[undefined, "odd", "even", "odd"], undefined, []]);
    });

    it("forgets the flying emotes and the taps when the page leaves the table", () => {
        receiveReactions([thrown(1, "gasp"), thrown(2, "shell")]);

        resetReactions();

        expect([flyingEmotes(), beatOf("shell")]).toEqual([[], undefined]);
    });
});
