import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Cue } from "./cues.ts";
import type { AudioPort, Voice } from "./sound.ts";
import { createTableSound, type TableSound } from "./tableSound.ts";
import type { Card, Chair, Table } from "../routes/(start)/tables.ts";

const OWN_SEAT = 1;
const OTHER_SEAT = 2;
const THIRD_SEAT = 3;
const CARD: Card = { suit: "kreuz", rank: "king" };
const SETTINGS = { muted: false, volume: 70 };

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
    }));
    return {
        id: "a".repeat(32),
        version: 2,
        chairs,
        watchers: 0,
        hand: null,
        result: null,
        passed_in: null,
        bock: null,
        ended: null,
    };
}

function soundAt(port: FakePort, options: { motion?: boolean } = {}): TableSound {
    return createTableSound({ port, settings: () => SETTINGS, motion: () => options.motion ?? false });
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

    it("starts later while the device allows motion than while it asks for none", () => {
        const still = new FakePort();
        const moving = new FakePort();

        soundAt(still, { motion: false }).forCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));
        soundAt(moving, { motion: true }).forCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

        expect(earliest(moving)).toBeGreaterThan(earliest(still));
    });
});

describe("cues without a sound", () => {
    it.each([
        { name: "an auction that ended", cues: [{ kind: "auction-ended" } satisfies Cue] },
        { name: "no cue at all", cues: [] },
    ])("start no voice for $name", ({ cues }) => {
        const port = new FakePort();

        soundAt(port).forCues(cues, tableSeenFrom(OWN_SEAT));

        expect(port.played).toEqual([]);
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
        const node = () => ({
            gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
            frequency: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
            Q: {},
            threshold: {},
            ratio: {},
            connect: <Next>(next: Next): Next => next,
            start: (at = 0) => started.push(at),
            stop: vi.fn(),
        });
        class StubContext {
            state = "suspended";
            currentTime = 0;
            sampleRate = 4;
            destination = node();
            createGain = node;
            createDynamicsCompressor = node;
            createBufferSource = node;
            createOscillator = node;
            createBiquadFilter = node;
            createBuffer = (_channels: number, length: number) => ({ getChannelData: () => new Float32Array(length) });
            resume = () => {
                this.state = "running";
                return Promise.resolve();
            };
        }
        const listeners = new Map<string, () => void>();
        vi.stubGlobal("window", {
            AudioContext: StubContext,
            navigator: {},
            document: { hidden: false },
            matchMedia: () => ({ matches: options.reducedMotion }),
            localStorage: { getItem: () => options.stored ?? null },
            addEventListener: (type: string, handler: () => void) => listeners.set(type, handler),
            removeEventListener: (type: string) => listeners.delete(type),
        });
        return { started, listeners };
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
        { reducedMotion: false, soundsAfterLanding: true },
        { reducedMotion: true, soundsAfterLanding: false },
    ])(
        "lets a card land before it sounds only while the device allows motion ($reducedMotion)",
        async ({ reducedMotion, soundsAfterLanding }) => {
            const { started, listeners } = stubBrowser({ reducedMotion });
            const { armSound, soundForCues } = await import("./tableSound.ts");
            armSound();
            listeners.get("keydown")?.();

            soundForCues([cardPlayedBy(OTHER_SEAT)], tableSeenFrom(OWN_SEAT));

            expect(started.length).toBeGreaterThan(0);
            expect(Math.min(...started) > 0.2).toBe(soundsAfterLanding);
        },
    );

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
