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

// A run tells each of its words in an update of its own, and says how long the voice has for it. On a table that
// stands still a word is due at once, so one recording fits exactly.
const UNTIL_THE_NEXT_WORD = { fits: RECORDING_SECONDS, tooShort: RECORDING_SECONDS / 2 };
const THE_LAST_WORD = Infinity;

describe("the voice of a run of words", () => {
    const saying = (options: { now?: () => number } = {}) => {
        const port = new FakePort();
        const sound = soundAt(port, { voice: true, ...options });
        const said = (): string[] => port.spoken.map(({ url }) => url);
        return { port, sound, said };
    };

    it("says a word that ends before the next word is told", () => {
        const { sound, said } = saying();

        sound.forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT), UNTIL_THE_NEXT_WORD.fits);

        expect(said()).toEqual([RECORDING_OF("voice.value18")]);
    });

    it("leaves a word unsaid that would not end before the next word is told, and still taps for it", () => {
        const { port, sound, said } = saying();

        sound.forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT), UNTIL_THE_NEXT_WORD.tooShort);

        expect(said()).toEqual([]);
        expect(port.played.length).toBeGreaterThan(0);
    });

    it("always says the last word, with every other word its update brought", () => {
        const { sound, said } = saying();

        sound.forCues([PASS, KONTRA_SAID], tableSeenFrom(OWN_SEAT), THE_LAST_WORD);

        expect(said()).toEqual([RECORDING_OF("voice.pass"), RECORDING_OF("voice.kontra")]);
    });

    it("says a word only once the voice has said what it was given before, so it never talks over itself", () => {
        let now = 0;
        const { port, sound } = saying({ now: () => now });
        sound.forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT));
        const firstEnds = (port.spoken[0]?.afterSeconds as number) + RECORDING_SECONDS;
        now = RECORDING_SECONDS / 2;

        sound.forCues([PASS], tableSeenFrom(OWN_SEAT), THE_LAST_WORD);

        expect(port.spoken).toHaveLength(2);
        expect(now + (port.spoken[1]?.afterSeconds as number)).toBeCloseTo(firstEnds);
    });

    it("leaves a word unsaid when the voice is not free in time to end it before the next word", () => {
        let now = 0;
        const { sound, said } = saying({ now: () => now });
        sound.forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT), UNTIL_THE_NEXT_WORD.fits);
        now = RECORDING_SECONDS / 2;

        sound.forCues([PASS], tableSeenFrom(OWN_SEAT), UNTIL_THE_NEXT_WORD.fits);

        expect(said()).toEqual([RECORDING_OF("voice.value18")]);
    });

    it("says a word at once when the voice has long said the ones before it", () => {
        let now = 0;
        const { port, sound } = saying({ now: () => now });
        sound.forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT), UNTIL_THE_NEXT_WORD.fits);
        const atOnce = port.spoken[0]?.afterSeconds;
        now = 10 * RECORDING_SECONDS;

        sound.forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT), UNTIL_THE_NEXT_WORD.fits);

        expect(port.spoken[1]?.afterSeconds).toBe(atOnce);
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
