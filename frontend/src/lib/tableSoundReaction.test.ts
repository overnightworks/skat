import { describe, expect, it } from "vitest";
import { MOTION_SETS } from "./motionSets.ts";
import { SOUND_SETS } from "./soundSets.ts";
import { earliest, FakePort, soundAt } from "./tableSound.fixtures.ts";

describe("the sound of a reaction", () => {
    it.each(["fire", "lamp"] as const)("sounds %s in the chosen set, at the full gain of a cue", (reaction) => {
        const port = new FakePort();

        soundAt(port, { soundSet: "stammtisch" }).forReaction(reaction);

        expect(port.played.map(({ voice }) => voice)).toEqual(SOUND_SETS.stammtisch.reactions[reaction](1));
    });

    it("lands an emote when it touches the felt and an object when it makes its first move, as late as its motion set says", () => {
        const [still, emote, object] = [new FakePort(), new FakePort(), new FakePort()];

        soundAt(still).forReaction("clap");
        soundAt(emote, { motion: "verspielt" }).forReaction("clap");
        soundAt(object, { motion: "verspielt" }).forReaction("coaster");

        expect(earliest(emote) - earliest(still)).toBeCloseTo(MOTION_SETS.verspielt.emoteLandsSeconds);
        expect(earliest(object) - earliest(still)).toBeCloseTo(MOTION_SETS.verspielt.objectMovesSeconds);
    });

    it("is silent on a muted device", () => {
        const port = new FakePort();

        soundAt(port, { muted: true }).forReaction("cheers");

        expect(port.played).toEqual([]);
    });
});
