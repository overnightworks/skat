import { describe, expect, it } from "vitest";
import { createSound, DEFAULT_SOUND_SETTINGS, type AudioPort, type SoundSettings, type Voice } from "./sound.ts";

const CLICK: Voice = { kind: "noise", at: 0, seconds: 0.05, frequency: 3000, quality: 1, gain: 0.5 };
const THUMP: Voice = { kind: "tone", wave: "sine", at: 0.1, seconds: 0.06, frequency: 170, gain: 0.2 };

class FakePort implements AudioPort {
    readyNow = true;
    resumed = 0;
    loudness: number[] = [];
    played: { voice: Voice; afterSeconds: number }[] = [];

    // A hidden window is ready only for a sound that was asked for there.
    hiddenWindow = false;

    ready(whenHidden: boolean): boolean {
        return this.readyNow && (whenHidden || !this.hiddenWindow);
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

    loaded: string[] = [];
    spoken: { url: string; afterSeconds: number }[] = [];

    loadRecordings(urls: readonly string[]): Promise<void> {
        this.loaded.push(...urls);
        return Promise.resolve();
    }

    playRecording(url: string, afterSeconds: number): void {
        this.spoken.push({ url, afterSeconds });
    }

    sea: number[] = [];

    setSea(level: number): void {
        this.sea.push(level);
    }
}

function soundOver(port: FakePort, settings: SoundSettings = DEFAULT_SOUND_SETTINGS) {
    return createSound(port, () => settings);
}

describe("play", () => {
    it("starts nothing in a hidden window unless the sound was asked for there", () => {
        const port = new FakePort();
        port.hiddenWindow = true;

        soundOver(port).play([CLICK]);
        expect(port.played).toEqual([]);

        soundOver(port).play([CLICK], { whenHidden: true });
        expect(port.played.map(({ voice }) => voice)).toEqual([CLICK]);
    });

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

describe("speak", () => {
    it("plays the recording a little after now and the delay asked for", () => {
        const port = new FakePort();

        soundOver(port).speak("/voice/achtzehn.mp3", 0.5);

        expect(port.spoken).toHaveLength(1);
        expect(port.spoken[0]?.url).toBe("/voice/achtzehn.mp3");
        expect(port.spoken[0]?.afterSeconds).toBeGreaterThan(0.5);
    });

    it.each([
        { name: "while muted", settings: { muted: true, volume: 70 }, ready: true },
        { name: "while the port is not ready", settings: DEFAULT_SOUND_SETTINGS, ready: false },
    ])("plays nothing $name", ({ settings, ready }) => {
        const port = new FakePort();
        port.readyNow = ready;

        soundOver(port, settings).speak("/voice/achtzehn.mp3", 0);

        expect(port.spoken).toEqual([]);
    });

    it("plays at the volume the player set", () => {
        const port = new FakePort();

        soundOver(port, { muted: false, volume: 100 }).speak("/voice/achtzehn.mp3", 0);

        expect(port.loudness).toEqual([1]);
    });
});

describe("prepare", () => {
    it("has the port load the recordings", async () => {
        const port = new FakePort();

        await soundOver(port).prepare(["/a.mp3", "/b.mp3"]);

        expect(port.loaded).toEqual(["/a.mp3", "/b.mp3"]);
    });
});

describe("sea", () => {
    const wanted = (port: FakePort, settings: SoundSettings = DEFAULT_SOUND_SETTINGS) => {
        const sound = soundOver(port, settings);
        sound.sea(true);
        return sound;
    };
    const lastLevel = (port: FakePort) => port.sea.at(-1);

    it("is silent until the table wants it", () => {
        const port = new FakePort();

        soundOver(port).sea(false);

        expect(lastLevel(port)).toBe(0);
    });

    it("runs under the volume the cues play by, quieter than a cue", () => {
        const port = new FakePort();
        const louder = new FakePort();

        wanted(port, { muted: false, volume: 40 });
        wanted(louder, { muted: false, volume: 80 });

        expect(lastLevel(port)).toBeGreaterThan(0);
        expect(lastLevel(louder)).toBeGreaterThan(lastLevel(port) as number);
        expect(lastLevel(louder)).toBeLessThan(1);
    });

    it("is silent while muted or at volume 0", () => {
        const muted = new FakePort();
        const zero = new FakePort();

        wanted(muted, { muted: true, volume: 70 });
        wanted(zero, { muted: false, volume: 0 });

        expect([lastLevel(muted), lastLevel(zero)]).toEqual([0, 0]);
    });

    it("fades out while the window is hidden and back when it is shown again", () => {
        const port = new FakePort();
        const sound = wanted(port);
        const shown = lastLevel(port);

        port.hiddenWindow = true;
        sound.sea(true);
        const hidden = lastLevel(port);
        port.hiddenWindow = false;
        sound.sea(true);

        expect([hidden, lastLevel(port)]).toEqual([0, shown]);
    });

    it("stays silent on a device that makes no sound, and starts once the first tap wakes it", async () => {
        const port = new FakePort();
        port.readyNow = false;
        const sound = wanted(port);
        expect(lastLevel(port)).toBe(0);

        port.readyNow = true;
        await sound.resume();

        expect(lastLevel(port)).toBeGreaterThan(0);
    });

    it("follows a changed volume at the next call", () => {
        const port = new FakePort();
        let settings: SoundSettings = { muted: false, volume: 30 };
        const sound = createSound(port, () => settings);
        sound.sea(true);
        const quiet = lastLevel(port) as number;

        settings = { muted: false, volume: 90 };
        sound.sea(true);

        expect(lastLevel(port)).toBeGreaterThan(quiet);
    });
});
