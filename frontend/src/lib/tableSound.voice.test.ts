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
});
