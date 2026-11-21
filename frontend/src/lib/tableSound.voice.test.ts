import { describe, expect, it } from "vitest";
import type { Cue } from "./cues.ts";
import {
    BID_EIGHTEEN,
    FakePort,
    KONTRA_SAID,
    OWN_SEAT,
    PASS,
    RECORDING_OF,
    RECORDING_SECONDS,
    soundAt,
    tableSeenFrom,
} from "./tableSound.fixtures.ts";

describe("how long the voice speaks the words of one update", () => {
    it("is until the last of them has been said, counted from the update", () => {
        const port = new FakePort();

        const spoken = soundAt(port, { voice: true, motion: "verspielt" }).forCues(
            [BID_EIGHTEEN, PASS],
            tableSeenFrom(OWN_SEAT),
        );

        const lastStarts = port.spoken.at(-1)?.afterSeconds as number;
        expect(spoken).toBeGreaterThanOrEqual(2 * RECORDING_SECONDS);
        expect(spoken).toBeLessThanOrEqual(lastStarts + RECORDING_SECONDS);
    });

    it.each([
        { name: "the voice is off", options: { voice: false }, cues: [BID_EIGHTEEN] },
        { name: "the update brought no word to say", options: { voice: true }, cues: [] },
    ])("is no time while $name", ({ options, cues }) => {
        expect(soundAt(new FakePort(), options).forCues(cues, tableSeenFrom(OWN_SEAT))).toBe(0);
    });
});

describe("the voice of one update", () => {
    it("says the words of one update one after another, each once the one before has ended", () => {
        const port = new FakePort();

        soundAt(port, { voice: true, motion: "verspielt" }).forCues(
            [BID_EIGHTEEN, PASS, KONTRA_SAID],
            tableSeenFrom(OWN_SEAT),
        );

        expect(port.spoken.map(({ url }) => url)).toEqual([
            RECORDING_OF("voice.value18"),
            RECORDING_OF("voice.pass"),
            RECORDING_OF("voice.kontra"),
        ]);
        const starts = port.spoken.map(({ afterSeconds }) => afterSeconds);
        expect(starts[1]).toBeGreaterThanOrEqual((starts[0] as number) + RECORDING_SECONDS);
        expect(starts[2]).toBeGreaterThanOrEqual((starts[1] as number) + RECORDING_SECONDS);
    });

    it("says the announced game after the words of its update, word by word", () => {
        const port = new FakePort();
        const announced: Cue = {
            kind: "game-announced",
            game: "herz",
            hand: true,
            ouvert: false,
            announcement: "schneider",
        };

        soundAt(port, { voice: true }).forCues([BID_EIGHTEEN, announced], tableSeenFrom(OWN_SEAT));

        expect(port.spoken.map(({ url }) => url)).toEqual(
            ["voice.value18", "voice.herz", "voice.hand", "voice.schneider"].map(RECORDING_OF),
        );
    });

    it("says the announced game as soon as the update arrives, motion or none", () => {
        const announced: Cue = {
            kind: "game-announced",
            game: "herz",
            hand: false,
            ouvert: false,
            announcement: "none",
        };
        const startsWith = (options: Parameters<typeof soundAt>[1]): number[] => {
            const port = new FakePort();
            soundAt(port, options).forCues([announced], tableSeenFrom(OWN_SEAT));
            return port.spoken.map(({ afterSeconds }) => afterSeconds);
        };

        expect(startsWith({ voice: true, motion: "verspielt" })).toEqual(startsWith({ voice: true }));
    });
});
