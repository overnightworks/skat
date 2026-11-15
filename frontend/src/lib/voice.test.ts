import { describe, expect, it } from "vitest";
import { cuesBetween, type Cue } from "./cues.ts";
import { EVERY_HAND_DEALT, FOREHAND, MIDDLEHAND, REARHAND, table } from "./cues.fixtures.ts";
import { everyRecording, grumbleOf, recordingOf, voiceKeyOf, type VoiceKey } from "./voice.ts";
import { languages, loadWords, sourceLanguage } from "./words/index.ts";
import { VALID_BIDS } from "./wire.ts";
import type { AuctionWord } from "../routes/(start)/tables.ts";

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

    it("is one of the grumbles for a nudged chair, whichever the pick", async () => {
        const catalog = await loadWords(sourceLanguage);
        const keys = [0, 1, 2, 3, 4, 5, 6].map((pick) => voiceKeyOf({ kind: "nudged", seat: SEAT, pick }));

        expect(new Set(keys).size).toBeGreaterThan(1);
        for (const key of keys) expect(Object.hasOwn(catalog, key as string)).toBe(true);
    });

    it("has a key in the catalog for every bid the auction allows", async () => {
        const catalog = await loadWords(sourceLanguage);

        for (const value of VALID_BIDS) {
            const cue: Cue = { kind: "bid-said", seat: SEAT, word: { action: "bid", value } };
            expect(Object.hasOwn(catalog, voiceKeyOf(cue) as string)).toBe(true);
        }
    });
});

const HOLD_VALUES = [18, 20, 22, 23, 24, 27, 264];
const SEATS = [0, 1, 2];

function said(action: "bid" | "hold", seat: number, value: number): Cue {
    return { kind: "bid-said", seat, word: { action, value } };
}

const TABLE_SEATS = [FOREHAND, MIDDLEHAND, REARHAND];

// The word the voice says on each page of a table when `speaker` says `action` at `value`: the one server update
// reaches every page, and each page is the table as its own chair sees it.
function wordsHeardOnEveryPage(speaker: number, action: "bid" | "hold", value: number): (string | undefined)[] {
    const spoken: AuctionWord[] = [{ seat: speaker, action, value }];
    const asSeenFrom = (own: number, version: number, words: AuctionWord[]) => {
        const seen = table(version, EVERY_HAND_DEALT, { declaring: null, spoken: words });
        return { ...seen, chairs: seen.chairs.map((chair) => ({ ...chair, is_mine: chair.seat === own })) };
    };

    return TABLE_SEATS.map((own) => {
        const heard = cuesBetween(asSeenFrom(own, 1, []), asSeenFrom(own, 2, spoken)).filter(
            (cue) => cue.kind === "bid-said",
        );
        return heard.length === 1 ? voiceKeyOf(heard[0] as Cue) : undefined;
    });
}

describe("the word the voice says for a hold", () => {
    it("is never a number but a confirmation of the catalog, whatever the value", async () => {
        const catalog = await loadWords(sourceLanguage);

        for (const seat of SEATS) {
            for (const value of HOLD_VALUES) {
                const key = voiceKeyOf(said("hold", seat, value)) as string;
                expect(key).toMatch(/^voice\.hold/);
                expect(Object.hasOwn(catalog, key)).toBe(true);
            }
        }
    });

    it("is the same confirmation on every page for the same hold", () => {
        for (const speaker of TABLE_SEATS) {
            for (const value of HOLD_VALUES) {
                const heard = wordsHeardOnEveryPage(speaker, "hold", value);

                expect(heard[0]).toMatch(/^voice\.hold/);
                expect(new Set(heard).size).toBe(1);
            }
        }
    });

    it("varies between holds, so a table does not hear one word every time", () => {
        const keys = SEATS.flatMap((seat) => HOLD_VALUES.map((value) => voiceKeyOf(said("hold", seat, value))));

        expect(new Set(keys).size).toBeGreaterThan(2);
    });
});

describe("the word the voice says for a bid of 23", () => {
    const keys = SEATS.map((seat) => voiceKeyOf(said("bid", seat, 23)));

    it("is dreiundzwanzig or Null, and both are said at some seat", () => {
        expect(new Set(keys)).toEqual(new Set(["voice.value23", "voice.null"]));
    });

    it("is the same word on every page for the same bid", () => {
        for (const speaker of TABLE_SEATS) expect(new Set(wordsHeardOnEveryPage(speaker, "bid", 23)).size).toBe(1);
    });

    it("is a key of the catalog either way", async () => {
        const catalog = await loadWords(sourceLanguage);

        for (const key of keys) expect(Object.hasOwn(catalog, key as string)).toBe(true);
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
