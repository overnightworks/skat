import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Cue } from "./cues.ts";
import { MOTION_SETS, type MotionSetId } from "./motionSets.ts";
import type { AudioPort, Voice } from "./sound.ts";
import { SOUND_SETS, type SoundSetId } from "./soundSets.ts";
import { createTableSound, type TableSound } from "./tableSound.ts";
import { everyRecording } from "./voice.ts";
import type { Card, Chair, Table } from "../routes/(start)/tables.ts";

const OWN_SEAT = 1;
const OTHER_SEAT = 2;
const THIRD_SEAT = 3;
const CARD: Card = { suit: "kreuz", rank: "king" };
const SETTINGS = { muted: false, volume: 70 };
const FUNKELN_VOICES = 3;
// Waking the device plays one silent sample, which the stand-in counts as a start.
const WAKING_SAMPLE_STARTS = 1;

class FakePort implements AudioPort {
    resumed = 0;
    played: { voice: Voice; afterSeconds: number }[] = [];

    ready(): boolean {
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

function soundAt(
    port: FakePort,
    options: { motion?: MotionSetId; soundSet?: SoundSetId; voice?: boolean } = {},
): TableSound {
    return createTableSound({
        port,
        settings: () => SETTINGS,
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

describe("cues without a sound", () => {
    it.each([
        { name: "an auction that ended", cues: [{ kind: "auction-ended" } satisfies Cue] },
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

    function stubBrowser(options: { reducedMotion: boolean; stored?: string }) {
        const started: number[] = [];
        const gains: { setValueAtTime: ReturnType<typeof vi.fn> }[] = [];
        const node = () => ({
            gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
            frequency: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
            Q: {},
            threshold: {},
            ratio: {},
            knee: {},
            attack: {},
            release: {},
            connect: <Next>(next: Next): Next => next,
            start: (at = 0) => started.push(at),
            stop: vi.fn(),
        });
        class StubContext {
            static made: StubContext[] = [];
            constructor() {
                StubContext.made.push(this);
            }

            state = "suspended";
            currentTime = 0;
            sampleRate = 4;
            destination = node();
            createGain = () => {
                const gain = node();
                gains.push(gain.gain);
                return gain;
            };
            createDynamicsCompressor = node;
            createBufferSource = node;
            createOscillator = node;
            createBiquadFilter = node;
            createBuffer = (_channels: number, length: number) => ({ getChannelData: () => new Float32Array(length) });
            decodeAudioData = vi.fn(() => Promise.resolve({}));
            resume = () => {
                this.state = "running";
                return Promise.resolve();
            };
        }
        const listeners = new Map<string, () => void>();
        vi.stubGlobal("window", {
            fetch: vi.fn(() => Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(1)) })),
            AudioContext: StubContext,
            navigator: {},
            document: { hidden: false },
            matchMedia: () => ({ matches: options.reducedMotion, addEventListener: vi.fn() }),
            localStorage: { getItem: () => options.stored ?? null },
            addEventListener: (type: string, handler: () => void) => listeners.set(type, handler),
            removeEventListener: (type: string) => listeners.delete(type),
        });
        const decodes = (): number =>
            StubContext.made.reduce((all, one) => all + one.decodeAudioData.mock.calls.length, 0);
        return {
            started,
            listeners,
            decodes,
            masterLoudness: () => gains[0]?.setValueAtTime.mock.calls[0]?.[0] as number,
        };
    }

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
