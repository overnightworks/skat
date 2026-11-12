import { describe, expect, it } from "vitest";
import { createSound, DEFAULT_SOUND_SETTINGS, type AudioPort, type SoundSettings, type Voice } from "./sound.ts";

const CLICK: Voice = { kind: "noise", at: 0, seconds: 0.05, frequency: 3000, quality: 1, gain: 0.5 };
const THUMP: Voice = { kind: "tone", wave: "sine", at: 0.1, seconds: 0.06, frequency: 170, gain: 0.2 };

class FakePort implements AudioPort {
    readyNow = true;
    resumed = 0;
    loudness: number[] = [];
    played: { voice: Voice; afterSeconds: number }[] = [];

    ready(): boolean {
        return this.readyNow;
    }

    resume(): Promise<void> {
        this.resumed += 1;
        return Promise.resolve();
    }

    setLoudness(gain: number): void {
        this.loudness.push(gain);
    }

    playVoice(voice: Voice, afterSeconds: number): void {
        this.played.push({ voice, afterSeconds });
    }
}

function soundOver(port: FakePort, settings: SoundSettings = DEFAULT_SOUND_SETTINGS) {
    return createSound(port, () => settings);
}

describe("play", () => {
    it("starts every voice of the list", () => {
        const port = new FakePort();

        soundOver(port).play([CLICK, THUMP]);

        expect(port.played.map(({ voice }) => voice)).toEqual([CLICK, THUMP]);
    });

    it("leaves a little room before the voices start", () => {
        const port = new FakePort();

        soundOver(port).play([CLICK]);

        expect(port.played[0]?.afterSeconds).toBeGreaterThan(0);
    });

    it("starts nothing while muted", () => {
        const port = new FakePort();

        soundOver(port, { muted: true, volume: 70 }).play([CLICK]);

        expect(port.played).toEqual([]);
    });

    it("starts nothing while the port is not ready", () => {
        const port = new FakePort();
        port.readyNow = false;

        soundOver(port).play([CLICK]);

        expect(port.played).toEqual([]);
        expect(port.loudness).toEqual([]);
    });

    it("sets full loudness at volume 100 and silence at volume 0", () => {
        const port = new FakePort();

        soundOver(port, { muted: false, volume: 100 }).play([CLICK]);
        soundOver(port, { muted: false, volume: 0 }).play([CLICK]);

        expect(port.loudness).toEqual([1, 0]);
    });

    it("is louder at a higher volume", () => {
        const port = new FakePort();

        soundOver(port, { muted: false, volume: 30 }).play([CLICK]);
        soundOver(port, { muted: false, volume: 80 }).play([CLICK]);

        const [quieter, louder] = port.loudness as [number, number];
        expect(louder).toBeGreaterThan(quieter);
    });

    it("reads the settings anew at every play", () => {
        const port = new FakePort();
        let settings: SoundSettings = { muted: true, volume: 70 };
        const sound = createSound(port, () => settings);

        sound.play([CLICK]);
        settings = { muted: false, volume: 70 };
        sound.play([CLICK]);

        expect(port.played).toHaveLength(1);
    });
});

describe("resume", () => {
    it("reaches the port", async () => {
        const port = new FakePort();

        await soundOver(port).resume();

        expect(port.resumed).toBe(1);
    });
});
