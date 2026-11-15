import { describe, expect, it } from "vitest";
import type { Cue } from "./cues.ts";
import { everyRecording, grumbleOf, recordingOf, voiceKeysOf, type VoiceKey } from "./voice.ts";
import { languages, loadWords, sourceLanguage } from "./words/index.ts";
import { VALID_BIDS } from "./wire.ts";

const SEAT = 1;
const RECORDING_SUFFIX = ".mp3";

describe("the word the voice says for a cue", () => {
    it.each([
        {
            name: "a bid",
            cue: { kind: "bid-said", seat: SEAT, word: { action: "bid", value: 18 } },
            key: "voice.value18",
        },
        {
            name: "a hold",
            cue: { kind: "bid-said", seat: SEAT, word: { action: "hold", value: 264 } },
            key: "voice.value264",
        },
        {
            name: "a pass",
            cue: { kind: "bid-said", seat: SEAT, word: { action: "pass", value: null } },
            key: "voice.pass",
        },
        { name: "Kontra", cue: { kind: "word-said", said: { seat: SEAT, word: "kontra" } }, key: "voice.kontra" },
        { name: "Re", cue: { kind: "word-said", said: { seat: SEAT, word: "re" } }, key: "voice.re" },
        { name: "Supra", cue: { kind: "word-said", said: { seat: SEAT, word: "supra" } }, key: "voice.supra" },
        { name: "Hirsch", cue: { kind: "word-said", said: { seat: SEAT, word: "hirsch" } }, key: "voice.hirsch" },
    ] satisfies { name: string; cue: Cue; key: VoiceKey }[])("is the key of $name", ({ cue, key }) => {
        expect(voiceKeysOf(cue)).toEqual([key]);
    });

    it.each([
        {
            name: "a suit game",
            game: { game: "karo", hand: false, ouvert: false, announcement: "none" },
            keys: ["karo"],
        },
        {
            name: "a Hand game with Schneider announced",
            game: { game: "herz", hand: true, ouvert: false, announcement: "schneider" },
            keys: ["herz", "hand", "schneider"],
        },
        {
            name: "Grand with Schwarz announced",
            game: { game: "grand", hand: false, ouvert: false, announcement: "schwarz" },
            keys: ["grand", "schwarz"],
        },
        {
            name: "a Null ouvert game",
            game: { game: "null", hand: false, ouvert: true, announcement: "none" },
            keys: ["null", "ouvert"],
        },
        {
            name: "a Null ouvert Hand game",
            game: { game: "null", hand: true, ouvert: true, announcement: "none" },
            keys: ["null", "ouvert", "hand"],
        },
        {
            name: "a Pik ouvert game, which includes Hand",
            game: { game: "pik", hand: true, ouvert: true, announcement: "none" },
            keys: ["pik", "ouvert"],
        },
    ] satisfies { name: string; game: Omit<Extract<Cue, { kind: "game-announced" }>, "kind">; keys: string[] }[])(
        "are the words of $name in the order the table reads it",
        ({ game, keys }) => {
            expect(voiceKeysOf({ kind: "game-announced", ...game })).toEqual(keys.map((key) => `voice.${key}`));
        },
    );

    it.each([
        { name: "a card", cue: { kind: "card-played", seat: SEAT, card: { suit: "kreuz", rank: "king" } } },
        { name: "the end of the auction", cue: { kind: "auction-ended" } },
        { name: "a refused give-up", cue: { kind: "give-up-refused", seats: [SEAT] } },
    ] satisfies { name: string; cue: Cue }[])("is nothing for $name", ({ cue }) => {
        expect(voiceKeysOf(cue)).toEqual([]);
    });

    it("is one of the grumbles for a nudged chair, whichever the pick", async () => {
        const catalog = await loadWords(sourceLanguage);
        const keys = [0, 1, 2, 3, 4, 5, 6].flatMap((pick) => voiceKeysOf({ kind: "nudged", seat: SEAT, pick }));

        expect(new Set(keys).size).toBeGreaterThan(1);
        for (const key of keys) expect(Object.hasOwn(catalog, key as string)).toBe(true);
    });

    it("has a key in the catalog for every bid the auction allows", async () => {
        const catalog = await loadWords(sourceLanguage);

        for (const value of VALID_BIDS) {
            const cue: Cue = { kind: "bid-said", seat: SEAT, word: { action: "bid", value } };
            expect(voiceKeysOf(cue).every((key) => Object.hasOwn(catalog, key))).toBe(true);
        }
    });
});

describe("the grumble of a nudged chair", () => {
    it("is the same line for the same pick and another line for the next pick", () => {
        expect([grumbleOf(7), grumbleOf(7)]).toEqual([grumbleOf(7), grumbleOf(7)]);
        expect(grumbleOf(8)).not.toBe(grumbleOf(7));
    });

    it("is a voice line for every pick, however large", () => {
        for (const pick of [0, 5, 10 ** 9]) expect(grumbleOf(pick)).toMatch(/^voice\./);
    });
});

// Every file shipped under voice/, whatever its kind, so a stray file or a second format fails the count.
const SHIPPED_FILES = Object.keys(import.meta.glob("./voice/*/*"));

function recordingsOf(language: string): string[] {
    const folder = `./voice/${language}/`;
    return SHIPPED_FILES.filter((path) => path.startsWith(folder))
        .map((path) => path.slice(folder.length))
        .sort();
}

describe.each(languages)("the recordings in %s", (language) => {
    it("each have a voice key in the catalog, and a key without a recording stays silent", async () => {
        const keys = Object.keys(await loadWords(language)).filter((key) => key.startsWith("voice."));
        const recorded = recordingsOf(language).map((file) => file.slice(0, -RECORDING_SUFFIX.length));

        expect(recorded.length).toBeGreaterThan(0);
        expect(recorded.filter((key) => !keys.includes(key))).toEqual([]);
    });
});

describe("the recordings of the page's language", () => {
    it("are found by key", () => {
        const recorded = recordingsOf(sourceLanguage).map((file) =>
            file.slice(0, -RECORDING_SUFFIX.length),
        ) as VoiceKey[];

        for (const key of recorded) expect(recordingOf(key)).toContain(key);
    });

    it("are all fetched in advance, and none of another language", () => {
        expect(everyRecording()).toHaveLength(recordingsOf(sourceLanguage).length);
    });

    it("have no recording for a key that was never recorded", () => {
        expect(recordingOf("voice.value0" as VoiceKey)).toBeUndefined();
    });
});
