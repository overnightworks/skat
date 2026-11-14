import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Cue } from "./cues.ts";
import { MOTION_SETS, type MotionSetId } from "./motionSets.ts";
import type { AudioPort, Voice } from "./sound.ts";
import { SOUND_SETS, type SoundSetId } from "./soundSets.ts";
import { createTableSound, type TableSound } from "./tableSound.ts";
import { everyRecording } from "./voice.ts";
import { stubBrowser } from "../testing/stubBrowser.ts";
import type { Card, Chair, LastTrick, Table } from "../routes/(start)/tables.ts";

const OWN_SEAT = 1;
const OTHER_SEAT = 2;
const THIRD_SEAT = 3;
const CARD: Card = { suit: "kreuz", rank: "king" };
const TRICK: LastTrick = { cards: [CARD, CARD, CARD], leader_seat: OWN_SEAT, taker_seat: OTHER_SEAT };
const SETTINGS = { muted: false, volume: 70 };
const FUNKELN_VOICES = 3;
// Waking the device plays one silent sample, which the stand-in counts as a start.
const WAKING_SAMPLE_STARTS = 1;

class FakePort implements AudioPort {
    resumed = 0;
    played: { voice: Voice; afterSeconds: number }[] = [];
    // What each sound asked of the window: true for a sound that is wanted while it is hidden.
    askedWhenHidden: boolean[] = [];

    ready(whenHidden: boolean): boolean {
        this.askedWhenHidden.push(whenHidden);
        return true;
    }

    resume(): Promise<void> {
        this.resumed += 1;
        return Promise.resolve();
    }

    setLoudness(): void {
        // The loudness is the engine's, not this module's.
    }

    playVoice(voice: Voice, afterSeconds: number): void {
        this.played.push({ voice, afterSeconds });
    }

    loaded: string[] = [];
    spoken: { url: string; afterSeconds: number }[] = [];

    loadRecordings(urls: readonly string[]): Promise<void> {
        this.loaded.push(...urls);
        return Promise.resolve();
    }

    playRecording(url: string, afterSeconds: number): void {
        this.spoken.push({ url, afterSeconds });
    }
}

function cardPlayedBy(seat: number): Cue {
    return { kind: "card-played", seat, card: CARD };
}

function tableSeenFrom(ownSeat: number): Table {
    const chairs = [OWN_SEAT, OTHER_SEAT, THIRD_SEAT].map((seat): Chair => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === ownSeat,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
        former_holder_name: null,
        is_mine_to_return: false,
        nudge: null,
    }));
    return {
        id: "a".repeat(32),
        version: 2,
        chairs,
        watchers: 0,
        opened_by_me: false,
        hand: null,
        result: null,
        passed_in: null,
        series: null,
        aborted: null,
        options: null,
        bock: null,
        ended: null,
    };
}

const RECORDING_OF = (key: string): string => `/voice/${key}.mp3`;

interface Options {
    motion?: MotionSetId;
    soundSet?: SoundSetId;
    voice?: boolean;
    muted?: boolean;
    background?: boolean;
    vibration?: boolean;
    vibrate?: (pattern: readonly number[]) => void;
}

function soundAt(port: FakePort, options: Options = {}): TableSound {
    return createTableSound({
        port,
        settings: () => ({ ...SETTINGS, muted: options.muted ?? false }),
        turnInBackground: () => options.background ?? false,
        vibrationOn: () => options.vibration ?? false,
        vibrate: options.vibrate ?? (() => undefined),
        soundSet: () => SOUND_SETS[options.soundSet ?? "leise"],
        motion: () => (options.motion === undefined ? undefined : MOTION_SETS[options.motion]),
        voiceOn: () => options.voice ?? false,
        recording: (key) => (key === "voice.supra" ? undefined : RECORDING_OF(key)),
        recordings: () => [RECORDING_OF("voice.kontra"), RECORDING_OF("voice.re")],
    });
}

const loudest = (port: FakePort): number => Math.max(...port.played.map(({ voice }) => voice.gain));
const earliest = (port: FakePort): number => Math.min(...port.played.map(({ voice }) => voice.at));

describe("the sound of a card", () => {
    it("is quieter for a card another chair played than for the viewer's own", () => {
        const own = new FakePort();
        const other = new FakePort();

        soundAt(own).forCues([cardPlayedBy(OWN_SEAT)], tableSeenFrom(OWN_SEAT));
        soundAt(other).forCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        expect(loudest(other)).toBeLessThan(loudest(own));
        expect(loudest(other)).toBeGreaterThan(0);
    });

    it("sounds one card after the other when an update lays two", () => {
        const port = new FakePort();
        const cues = [cardPlayedBy(OTHER_SEAT), cardPlayedBy(THIRD_SEAT)];

        soundAt(port).forCues(cues, tableSeenFrom(OWN_SEAT));

        const first = port.played.filter((_, index) => index < port.played.length / 2);
        const second = port.played.filter((_, index) => index >= port.played.length / 2);
        expect(Math.min(...second.map(({ voice }) => voice.at))).toBeGreaterThan(
            Math.max(...first.map(({ voice }) => voice.at)),
        );
    });

    it("starts later in the set that lands later and not at all later without a motion set", () => {
        const [still, quiet, playful] = [new FakePort(), new FakePort(), new FakePort()];

        soundAt(still).forCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));
        soundAt(quiet, { motion: "dezent" }).forCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));
        soundAt(playful, { motion: "verspielt" }).forCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        expect(earliest(quiet)).toBeGreaterThan(earliest(still));
        expect(earliest(playful)).toBeGreaterThan(earliest(quiet));
    });

    it("sounds differently in each sound set", () => {
        const heard = (soundSet: SoundSetId): string => {
            const port = new FakePort();
            soundAt(port, { soundSet }).forCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));
            return JSON.stringify(port.played);
        };

        const sets = Object.keys(SOUND_SETS) as SoundSetId[];

        expect(new Set(sets.map(heard)).size).toBe(sets.length);
    });

    it.each(Object.keys(SOUND_SETS) as SoundSetId[])(
        "previews the card of the set %s at once and at the player's own level",
        async (soundSet) => {
            const preview = new FakePort();
            const own = new FakePort();

            await soundAt(preview, { soundSet, motion: "verspielt" }).preview();
            soundAt(own, { soundSet }).forCues([cardPlayedBy(OWN_SEAT)], tableSeenFrom(OWN_SEAT));

            expect(preview.resumed).toBe(1);
            expect(preview.played).toEqual(own.played);
        },
    );
});

const SITTER = { seat: THIRD_SEAT, name: "Nova", agent: true, mine: false };
const CHAIR_TAKEN: Cue = { kind: "chair-taken", inHand: false, ...SITTER };
const CHAIR_STOOD: Cue = { kind: "chair-stood", ...SITTER };
const CHAIR_OPENED: Cue = { kind: "chair-opened", ...SITTER };
const CHAIR_CUES = [CHAIR_TAKEN, CHAIR_STOOD, CHAIR_OPENED];
// Tone voices below the bells' overtones, in the order they start.
const BELL_NOTES_OF = (port: FakePort): number[] =>
    port.played
        .filter(({ voice }) => voice.kind === "tone" && [587, 784, 1047].includes(voice.frequency))
        .sort((first, second) => first.voice.at - second.voice.at)
        .map(({ voice }) => (voice as Extract<Voice, { kind: "tone" }>).frequency);

describe("the sound of a chair", () => {
    it.each(
        Object.keys(SOUND_SETS).flatMap((soundSet) =>
            CHAIR_CUES.map((cue) => ({ soundSet: soundSet as SoundSetId, cue, name: `${cue.kind} in ${soundSet}` })),
        ),
    )("sounds $name", ({ soundSet, cue }) => {
        const port = new FakePort();

        soundAt(port, { soundSet }).forCues([cue], tableSeenFrom(OWN_SEAT));

        expect(port.played.length).toBeGreaterThan(0);
    });

    it.each(CHAIR_CUES.map((cue) => ({ cue, name: cue.kind })))(
        "sounds $name differently in each sound set",
        ({ cue }) => {
            const heard = (soundSet: SoundSetId): string => {
                const port = new FakePort();
                soundAt(port, { soundSet }).forCues([cue], tableSeenFrom(OWN_SEAT));
                return JSON.stringify(port.played);
            };

            const sets = Object.keys(SOUND_SETS) as SoundSetId[];

            expect(new Set(sets.map(heard)).size).toBe(sets.length);
        },
    );

    it.each(Object.keys(SOUND_SETS) as SoundSetId[])(
        "stands up quieter than it sits down in the set %s",
        (soundSet) => {
            const [sits, stands] = [new FakePort(), new FakePort()];

            soundAt(sits, { soundSet }).forCues([CHAIR_TAKEN], tableSeenFrom(OWN_SEAT));
            soundAt(stands, { soundSet }).forCues([CHAIR_STOOD], tableSeenFrom(OWN_SEAT));

            expect(loudest(stands)).toBeLessThan(loudest(sits));
        },
    );

    it("rings the stand bells, the second lower, in Funkeln when a chair opens", () => {
        const port = new FakePort();

        soundAt(port, { soundSet: "funkeln" }).forCues([CHAIR_OPENED], tableSeenFrom(OWN_SEAT));

        expect(BELL_NOTES_OF(port)).toEqual([784, 587]);
    });

    it("rings the sit bells, the second higher, in Funkeln when a chair is taken", () => {
        const port = new FakePort();

        soundAt(port, { soundSet: "funkeln" }).forCues([CHAIR_TAKEN], tableSeenFrom(OWN_SEAT));

        expect(BELL_NOTES_OF(port)).toEqual([784, 1047]);
    });

    it.each(CHAIR_CUES.map((cue) => ({ cue, name: cue.kind })))(
        "sounds $name at the same time whatever motion set the table moves in",
        ({ cue }) => {
            const [still, quiet, playful] = [new FakePort(), new FakePort(), new FakePort()];

            soundAt(still).forCues([cue], tableSeenFrom(OWN_SEAT));
            soundAt(quiet, { motion: "dezent" }).forCues([cue], tableSeenFrom(OWN_SEAT));
            soundAt(playful, { motion: "verspielt" }).forCues([cue], tableSeenFrom(OWN_SEAT));

            expect(earliest(quiet)).toBe(earliest(still));
            expect(earliest(playful)).toBe(earliest(still));
        },
    );

    it("says nothing with the voice on", () => {
        const port = new FakePort();

        soundAt(port, { voice: true }).forCues(CHAIR_CUES, tableSeenFrom(OWN_SEAT));

        expect(port.spoken).toEqual([]);
    });
});

describe("the sound of a swept trick", () => {
    it.each(Object.keys(SOUND_SETS) as SoundSetId[])("is the sweep of the set %s", (soundSet) => {
        const port = new FakePort();

        soundAt(port, { soundSet }).forGlide();

        expect(port.played.map(({ voice }) => voice)).toEqual(SOUND_SETS[soundSet].voices["trick-swept"](1));
    });

    it("waits for the trick to gather in a set that gathers it, and not otherwise", () => {
        const [quiet, playful] = [new FakePort(), new FakePort()];

        soundAt(quiet, { motion: "dezent" }).forGlide();
        soundAt(playful, { motion: "verspielt" }).forGlide();

        expect(earliest(quiet)).toBe(0);
        expect(earliest(playful)).toBe(MOTION_SETS.verspielt.trickGatherSeconds);
    });

    it("is silent while muted", () => {
        const port = new FakePort();

        soundAt(port, { muted: true }).forGlide();

        expect(port.played).toEqual([]);
    });
});

describe("cues without a sound", () => {
    it.each([
        { name: "an auction that ended", cues: [{ kind: "auction-ended" } satisfies Cue] },
        { name: "a trick taken", cues: [{ kind: "trick-taken", trick: TRICK } satisfies Cue] },
        { name: "a give-up refused", cues: [{ kind: "give-up-refused", seats: [OTHER_SEAT] } satisfies Cue] },
        { name: "no cue at all", cues: [] },
    ])("start no voice for $name", ({ cues }) => {
        const port = new FakePort();

        soundAt(port, { motion: "verspielt", voice: true }).forCues(cues, tableSeenFrom(OWN_SEAT));

        expect(port.played).toEqual([]);
        expect(port.spoken).toEqual([]);
    });
});

const BID_EIGHTEEN: Cue = { kind: "bid-said", seat: OTHER_SEAT, word: { action: "bid", value: 18 } };
const PASS: Cue = { kind: "bid-said", seat: OTHER_SEAT, word: { action: "pass", value: null } };
const KNOCKS_OF_LEISE = 6;
const KONTRA_SAID: Cue = { kind: "word-said", said: { seat: OTHER_SEAT, word: "kontra" } };

describe("the sound of a bid", () => {
    it.each(Object.keys(SOUND_SETS) as SoundSetId[])("taps in the set %s", (soundSet) => {
        const port = new FakePort();

        soundAt(port, { soundSet }).forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT));

        expect(port.played.length).toBeGreaterThan(0);
    });

    it("sounds differently in each sound set", () => {
        const heard = (soundSet: SoundSetId): string => {
            const port = new FakePort();
            soundAt(port, { soundSet }).forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT));
            return JSON.stringify(port.played);
        };

        const sets = Object.keys(SOUND_SETS) as SoundSetId[];

        expect(new Set(sets.map(heard)).size).toBe(sets.length);
    });

    it("taps nothing for a pass, which has no bubble", () => {
        const port = new FakePort();

        soundAt(port).forCues([PASS], tableSeenFrom(OWN_SEAT));

        expect(port.played).toEqual([]);
    });

    it("taps when the bubble has sprung in the set the table moves in", () => {
        const [still, quiet] = [new FakePort(), new FakePort()];

        soundAt(still).forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT));
        soundAt(quiet, { motion: "dezent" }).forCues([BID_EIGHTEEN], tableSeenFrom(OWN_SEAT));

        expect(earliest(quiet)).toBeGreaterThan(earliest(still));
    });
});

describe("the sound of a word of Kontra", () => {
    it.each(Object.keys(SOUND_SETS) as SoundSetId[])("knocks twice in the set %s", (soundSet) => {
        const port = new FakePort();

        soundAt(port, { soundSet }).forCues([KONTRA_SAID], tableSeenFrom(OWN_SEAT));

        const knocks = port.played.filter(({ voice }) => voice.kind === "tone" && voice.frequency === 190);
        expect(knocks).toHaveLength(2);
    });

    it("knocks when the stamp has landed in the set the table moves in", () => {
        const [still, quiet, playful] = [new FakePort(), new FakePort(), new FakePort()];

        soundAt(still).forCues([KONTRA_SAID], tableSeenFrom(OWN_SEAT));
        soundAt(quiet, { motion: "dezent" }).forCues([KONTRA_SAID], tableSeenFrom(OWN_SEAT));
        soundAt(playful, { motion: "verspielt" }).forCues([KONTRA_SAID], tableSeenFrom(OWN_SEAT));

        expect(earliest(quiet)).toBeGreaterThan(earliest(still));
        expect(earliest(playful)).toBeGreaterThan(earliest(quiet));
    });
});

describe("the voice", () => {
    const SUPRA_SAID: Cue = { kind: "word-said", said: { seat: OTHER_SEAT, word: "supra" } };

    it.each([
        { name: "a bid", cue: BID_EIGHTEEN, key: "voice.value18" },
        { name: "a pass", cue: PASS, key: "voice.pass" },
        { name: "a word of Kontra", cue: KONTRA_SAID, key: "voice.kontra" },
    ])("says $name from the recording bound to its key", ({ cue, key }) => {
        const port = new FakePort();

        soundAt(port, { voice: true }).forCues([cue], tableSeenFrom(OWN_SEAT));

        expect(port.spoken.map(({ url }) => url)).toEqual([RECORDING_OF(key)]);
    });

    it("says nothing while the voice is off, and the taps sound all the same", () => {
        const port = new FakePort();

        soundAt(port, { voice: false }).forCues([BID_EIGHTEEN, KONTRA_SAID], tableSeenFrom(OWN_SEAT));

        expect(port.spoken).toEqual([]);
        expect(port.played.length).toBeGreaterThan(0);
    });

    it.each([
        { name: "a card", cues: [cardPlayedBy(OTHER_SEAT)] },
        { name: "a word without a recording", cues: [SUPRA_SAID] },
    ])("says nothing for $name", ({ cues }) => {
        const port = new FakePort();

        soundAt(port, { voice: true }).forCues(cues, tableSeenFrom(OWN_SEAT));

        expect(port.spoken).toEqual([]);
    });

    it("says a word when the stamp has landed in the set the table moves in", () => {
        const [still, playful] = [new FakePort(), new FakePort()];

        soundAt(still, { voice: true }).forCues([KONTRA_SAID], tableSeenFrom(OWN_SEAT));
        soundAt(playful, { voice: true, motion: "verspielt" }).forCues([KONTRA_SAID], tableSeenFrom(OWN_SEAT));

        expect((playful.spoken[0]?.afterSeconds ?? 0) - (still.spoken[0]?.afterSeconds ?? 0)).toBeCloseTo(
            MOTION_SETS.verspielt.stampLandsSeconds,
        );
    });

    it("fetches the recordings at a tap while it is on and not while it is off", async () => {
        const [on, off] = [new FakePort(), new FakePort()];

        await soundAt(on, { voice: true }).prepareVoice();
        await soundAt(off, { voice: false }).prepareVoice();

        expect(on.loaded).toEqual([RECORDING_OF("voice.kontra"), RECORDING_OF("voice.re")]);
        expect(off.loaded).toEqual([]);
    });

    it("fetches the recordings after the device is woken by a tap", async () => {
        const port = new FakePort();
        const handlers: (() => void)[] = [];
        soundAt(port, { voice: true }).arm({
            addEventListener: (_type: string, handler: () => void) => handlers.push(handler),
            removeEventListener: () => undefined,
        });

        handlers[0]?.();
        await vi.waitFor(() => {
            expect(port.loaded).toHaveLength(2);
        });
    });
});

describe("arming", () => {
    function fakeTarget() {
        const handlers = new Map<string, (() => void)[]>();
        return {
            handlers,
            addEventListener(type: string, handler: () => void) {
                handlers.set(type, [...(handlers.get(type) ?? []), handler]);
            },
            removeEventListener(type: string, handler: () => void) {
                handlers.set(
                    type,
                    (handlers.get(type) ?? []).filter((held) => held !== handler),
                );
            },
            fire(type: string) {
                for (const handler of handlers.get(type) ?? []) handler();
            },
        };
    }

    it.each(["pointerup", "keydown"])("resumes the port at a %s", (type) => {
        const port = new FakePort();
        const target = fakeTarget();
        soundAt(port).arm(target);

        target.fire(type);

        expect(port.resumed).toBe(1);
    });

    it("stops resuming once the returned function ran", () => {
        const port = new FakePort();
        const target = fakeTarget();
        const disarm = soundAt(port).arm(target);

        disarm();
        target.fire("pointerup");
        target.fire("keydown");

        expect(port.resumed).toBe(0);
    });
});

describe("the page's sound", () => {
    beforeEach(() => {
        vi.resetModules();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("sounds a card only after the first tap and none before it", async () => {
        const { started, listeners } = stubBrowser({ reducedMotion: true });
        const { armSound, soundForCues } = await import("./tableSound.ts");
        const disarm = armSound();

        soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));
        const before = started.length;
        listeners.get("pointerup")?.();
        soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        expect(before).toBe(0);
        expect(started.length).toBeGreaterThan(0);
        disarm();
        expect(listeners.size).toBe(0);
    });

    it("sounds the sweep of a trick only after the first tap and none before it", async () => {
        const { started, listeners } = stubBrowser({ reducedMotion: true });
        const { armSound, soundForGlide } = await import("./tableSound.ts");
        armSound();

        soundForGlide();
        const before = started.length;
        listeners.get("pointerup")?.();
        soundForGlide();

        expect(before).toBe(0);
        expect(started.length).toBeGreaterThan(0);
    });

    it.each([
        { reducedMotion: false, replayMotion: false, soundsAfterLanding: true },
        { reducedMotion: true, replayMotion: false, soundsAfterLanding: false },
        { reducedMotion: true, replayMotion: true, soundsAfterLanding: true },
    ])(
        "lets a card land before it sounds only while the table moves (device reduces $reducedMotion, player overrides $replayMotion)",
        async ({ reducedMotion, replayMotion, soundsAfterLanding }) => {
            const { started, listeners } = stubBrowser({
                reducedMotion,
                stored: JSON.stringify({ replayMotion }),
            });
            const { armSound, soundForCues } = await import("./tableSound.ts");
            armSound();
            listeners.get("keydown")?.();

            soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

            expect(started.length).toBeGreaterThan(0);
            expect(Math.min(...started) > 0.1).toBe(soundsAfterLanding);
        },
    );

    it.each([
        { stored: {}, voices: 2 },
        { stored: { soundSet: "stammtisch" }, voices: 3 },
        { stored: { soundSet: "funkeln" }, voices: 3 },
        { stored: { soundSet: "nope" }, voices: 2 },
    ])("sounds the card of the stored sound set $stored", async ({ stored, voices }) => {
        const { started, listeners } = stubBrowser({ reducedMotion: true, stored: JSON.stringify(stored) });
        const { armSound, soundForCues } = await import("./tableSound.ts");
        armSound();
        listeners.get("keydown")?.();

        soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        expect(started).toHaveLength(voices);
    });

    it("says a word of Kontra from its recording once the voice is stored on and the recordings are fetched", async () => {
        const { started, listeners, decodes } = stubBrowser({
            reducedMotion: true,
            stored: JSON.stringify({ voice: true }),
        });
        const { armSound, soundForCues } = await import("./tableSound.ts");
        armSound();
        listeners.get("keydown")?.();
        await vi.waitFor(() => {
            expect(decodes()).toBe(everyRecording().length);
        });
        const before = started.length;

        soundForCues([KONTRA_SAID], tableSeenFrom(OWN_SEAT));

        expect(started.length - before).toBe(KNOCKS_OF_LEISE + 1);
    });

    it("fetches no recording while the voice is off", async () => {
        const { listeners, decodes } = stubBrowser({ reducedMotion: true });
        const { armSound, prepareVoice } = await import("./tableSound.ts");
        armSound();
        listeners.get("keydown")?.();

        await prepareVoice();

        expect(decodes()).toBe(0);
    });

    async function loudnessOfStored(stored: object): Promise<number> {
        vi.resetModules();
        const { masterLoudness, listeners } = stubBrowser({ reducedMotion: true, stored: JSON.stringify(stored) });
        const { armSound, soundForCues } = await import("./tableSound.ts");
        armSound();
        listeners.get("keydown")?.();

        soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        return masterLoudness();
    }

    it("plays quieter for a lower stored volume and silent for a stored zero", async () => {
        const standard = await loudnessOfStored({});

        expect(await loudnessOfStored({ volume: 20 })).toBeLessThan(standard);
        expect(await loudnessOfStored({ volume: 0 })).toBe(0);
    });

    it("plays an unset volume as loudly as an explicit default", async () => {
        const standard = await loudnessOfStored({});

        expect(await loudnessOfStored({ volume: 70 })).toBeCloseTo(standard);
        expect(standard).toBeGreaterThan(0);
    });

    it("previews the chosen sound set after the page woke its sound", async () => {
        const { started } = stubBrowser({ reducedMotion: true, stored: JSON.stringify({ soundSet: "funkeln" }) });
        const { previewSound } = await import("./tableSound.ts");

        await previewSound();

        expect(started).toHaveLength(FUNKELN_VOICES + WAKING_SAMPLE_STARTS);
    });

    it.each([
        { name: "the tap arms it first", armFirst: true },
        { name: "a cue comes first", armFirst: false },
    ])("sounds no card while the device holds a muted table when $name", async ({ armFirst }) => {
        const { started, listeners } = stubBrowser({ reducedMotion: true, stored: JSON.stringify({ muted: true }) });
        const { armSound, soundForCues } = await import("./tableSound.ts");
        if (armFirst) armSound();

        soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));
        if (!armFirst) armSound();
        listeners.get("pointerup")?.();
        soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        expect(started).toEqual([]);
    });

    it("sounds a card when the device holds nothing", async () => {
        const { started, listeners } = stubBrowser({ reducedMotion: true });
        const { armSound, soundForCues } = await import("./tableSound.ts");
        armSound();
        listeners.get("pointerup")?.();

        soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        expect(started.length).toBeGreaterThan(0);
    });
});

const TURN: Cue = { kind: "turn-came" };

describe("the sound of the viewer's turn", () => {
    it.each(Object.keys(SOUND_SETS) as SoundSetId[])("is the turn of the set %s", (soundSet) => {
        const port = new FakePort();

        soundAt(port, { soundSet }).forTurn([]);

        expect(port.played.map(({ voice }) => voice)).toEqual(SOUND_SETS[soundSet].voices["turn-came"](1));
    });

    it("sounds nothing when the cue arrives, since the stage hands the turn over when it has settled", () => {
        const port = new FakePort();

        soundAt(port, { motion: "verspielt" }).forCues([TURN], tableSeenFrom(OWN_SEAT));

        expect(port.played).toEqual([]);
    });

    it("waits for the card another chair laid to land, and for nothing when no cue came with it", () => {
        const [after, alone] = [new FakePort(), new FakePort()];

        soundAt(after, { motion: "verspielt" }).forTurn([cardPlayedBy(OTHER_SEAT)]);
        soundAt(alone, { motion: "verspielt" }).forTurn([]);

        expect(earliest(after)).toBe(MOTION_SETS.verspielt.cardLandsSeconds);
        expect(earliest(alone)).toBe(0);
    });

    it("does not wait without a motion set", () => {
        const port = new FakePort();

        soundAt(port).forTurn([cardPlayedBy(OTHER_SEAT)]);

        expect(earliest(port)).toBe(0);
    });

    it.each([
        { name: "is not wanted in a hidden window by default", background: false },
        { name: "is wanted in a hidden window when the player asked for it", background: true },
    ])("$name", ({ background }) => {
        const port = new FakePort();

        soundAt(port, { background }).forTurn([]);

        expect(port.askedWhenHidden).toEqual([background]);
    });

    it("is silent while muted", () => {
        const port = new FakePort();

        soundAt(port, { muted: true, background: true }).forTurn([]);

        expect(port.played).toEqual([]);
    });

    it("vibrates once for the turn when the player switched vibration on, even while muted", () => {
        const patterns: (readonly number[])[] = [];

        soundAt(new FakePort(), { vibration: true, muted: true, vibrate: (pattern) => patterns.push(pattern) }).forTurn(
            [],
        );

        expect(patterns).toHaveLength(1);
        expect(patterns[0]?.reduce((sum, each) => sum + each, 0)).toBeGreaterThan(0);
    });

    it("does not vibrate while vibration is off", () => {
        const patterns: (readonly number[])[] = [];

        soundAt(new FakePort(), { vibrate: (pattern) => patterns.push(pattern) }).forTurn([]);

        expect(patterns).toEqual([]);
    });
});

describe("the sound of a deal", () => {
    const DEALT: Cue = { kind: "dealt" };

    it.each(Object.keys(SOUND_SETS) as SoundSetId[])("is the deal of the set %s", (soundSet) => {
        const port = new FakePort();

        soundAt(port, { soundSet }).forCues([DEALT], tableSeenFrom(OWN_SEAT));

        expect(port.played.map(({ voice }) => voice)).toEqual(SOUND_SETS[soundSet].voices.dealt(1));
    });

    it("does not wait for the motion set, since the cards fly in with the cue", () => {
        const [still, playful] = [new FakePort(), new FakePort()];

        soundAt(still).forCues([DEALT], tableSeenFrom(OWN_SEAT));
        soundAt(playful, { motion: "verspielt" }).forCues([DEALT], tableSeenFrom(OWN_SEAT));

        expect(playful.played).toEqual(still.played);
    });
});

describe("the sound of a result", () => {
    const appeared = (won: boolean, counts = true): Cue => ({ kind: "result-appeared", ordinal: 3, won, counts });
    const heard = (port: FakePort): Voice[] => port.played.map(({ voice }) => voice);

    it.each([
        { name: "a win", won: true, moment: "result-won" },
        { name: "a loss", won: false, moment: "result-lost" },
    ] as const)("stamps $name with the voices of the set", ({ won, moment }) => {
        const port = new FakePort();

        soundAt(port).forCues([appeared(won, false)], tableSeenFrom(OWN_SEAT));

        expect(heard(port)).toEqual(SOUND_SETS.leise.voices[moment](1));
    });

    it.each(Object.keys(MOTION_SETS) as MotionSetId[])("stamps when the card of the set %s has risen", (motion) => {
        const port = new FakePort();

        soundAt(port, { motion }).forCues([appeared(true, false)], tableSeenFrom(OWN_SEAT));

        expect(earliest(port)).toBe(MOTION_SETS[motion].resultLandsSeconds);
    });

    it.each(Object.keys(MOTION_SETS) as MotionSetId[])("ticks while the gains count up in the set %s", (motion) => {
        const stamped = new FakePort();
        const counted = new FakePort();

        soundAt(stamped, { motion }).forCues([appeared(true, false)], tableSeenFrom(OWN_SEAT));
        soundAt(counted, { motion }).forCues([appeared(true)], tableSeenFrom(OWN_SEAT));

        const ticks = counted.played.slice(stamped.played.length).map(({ voice }) => voice);
        expect(ticks.map((voice) => voice.at)).toEqual(
            SOUND_SETS.leise
                .counts(1, MOTION_SETS[motion].countSeconds)
                .map((voice) => voice.at + MOTION_SETS[motion].countStartsSeconds),
        );
    });

    it.each([
        { name: "no motion set is in force, where nothing counts", motion: undefined, counts: true },
        { name: "no seat gained anything", motion: "verspielt", counts: false },
    ] as const)("does not tick when $name", ({ motion, counts }) => {
        const stamped = new FakePort();
        const port = new FakePort();

        soundAt(stamped, { motion }).forCues([appeared(true, false)], tableSeenFrom(OWN_SEAT));
        soundAt(port, { motion }).forCues([appeared(true, counts)], tableSeenFrom(OWN_SEAT));

        expect(port.played).toEqual(stamped.played);
    });
});
