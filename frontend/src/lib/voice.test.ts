import { describe, expect, it } from "vitest";
import type { Cue } from "./cues.ts";
import { everyRecording, recordingOf, voiceKeyOf, type VoiceKey } from "./voice.ts";
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
        expect(voiceKeyOf(cue)).toBe(key);
    });

    it.each([
        { name: "a card", cue: { kind: "card-played", seat: SEAT, card: { suit: "kreuz", rank: "king" } } },
        { name: "the end of the auction", cue: { kind: "auction-ended" } },
        { name: "a refused give-up", cue: { kind: "give-up-refused", seats: [SEAT] } },
    ] satisfies { name: string; cue: Cue }[])("is nothing for $name", ({ cue }) => {
        expect(voiceKeyOf(cue)).toBeUndefined();
    });

    it("has a key in the catalog for every bid the auction allows", async () => {
        const catalog = await loadWords(sourceLanguage);

        for (const value of VALID_BIDS) {
            const cue: Cue = { kind: "bid-said", seat: SEAT, word: { action: "bid", value } };
            expect(Object.hasOwn(catalog, voiceKeyOf(cue) as string)).toBe(true);
        }
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
    it("are exactly one per voice key of the catalog, and none lacks a key", async () => {
        const keys = Object.keys(await loadWords(language)).filter((key) => key.startsWith("voice."));

        expect(recordingsOf(language)).toEqual(keys.map((key) => `${key}${RECORDING_SUFFIX}`).sort());
        expect(keys.length).toBeGreaterThan(0);
    });
});

describe("the recordings of the page's language", () => {
    it("are found by key", async () => {
        const keys = Object.keys(await loadWords(sourceLanguage)).filter((key) =>
            key.startsWith("voice."),
        ) as VoiceKey[];

        for (const key of keys) expect(recordingOf(key)).toContain(key);
    });

    it("are all fetched in advance, and none of another language", async () => {
        const keys = Object.keys(await loadWords(sourceLanguage)).filter((key) => key.startsWith("voice."));

        expect(everyRecording()).toHaveLength(keys.length);
    });

    it("have no recording for a key that was never recorded", () => {
        expect(recordingOf("voice.value0" as VoiceKey)).toBeUndefined();
    });
});
