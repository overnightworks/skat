import { beforeEach, describe, expect, it } from "vitest";
import type { Voice } from "./sound.ts";
import {
    CEILING_DECIBELS,
    ceilingCurve,
    createWebAudioPort,
    LIMITER_THRESHOLD_DECIBELS,
    type AudioEnvironment,
} from "./webAudio.ts";

const SAMPLE_RATE = 8;
const NOW = 5;

class FakeParam {
    value = 0;
    readonly ramps: { value: number; at: number }[] = [];
    readonly sets: { value: number; at: number }[] = [];

    setValueAtTime(value: number, at: number): void {
        this.sets.push({ value, at });
    }

    exponentialRampToValueAtTime(value: number, at: number): void {
        this.ramps.push({ value, at });
    }

    readonly targets: { value: number; at: number; timeConstant: number }[] = [];

    setTargetAtTime(value: number, at: number, timeConstant: number): void {
        this.targets.push({ value, at, timeConstant });
    }
}

class FakeNode {
    curve: Float32Array | null = null;
    oversample = "none";
    readonly gain = new FakeParam();
    readonly frequency = new FakeParam();
    readonly Q = new FakeParam();
    readonly threshold = new FakeParam();
    readonly ratio = new FakeParam();
    readonly knee = new FakeParam();
    readonly attack = new FakeParam();
    readonly release = new FakeParam();
    type = "";
    loop = false;
    buffer: unknown;
    startedAt: number | undefined;
    stoppedAt: number | undefined;
    readonly connectedTo: unknown[] = [];

    connect<Next>(next: Next): Next {
        this.connectedTo.push(next);
        return next;
    }

    start(at = 0): void {
        this.startedAt = at;
    }

    stop(at: number): void {
        this.stoppedAt = at;
    }
}

class FakeContext {
    static made: FakeContext[] = [];
    static resumeRejects = false;

    state = "suspended";
    currentTime = NOW;
    sampleRate = SAMPLE_RATE;
    resumes = 0;
    readonly destination = new FakeNode();
    readonly sources: FakeNode[] = [];
    readonly oscillators: FakeNode[] = [];
    readonly filters: FakeNode[] = [];
    readonly gains: FakeNode[] = [];
    readonly compressors: FakeNode[] = [];
    readonly shapers: FakeNode[] = [];
    readonly buffers: { samples: Float32Array }[] = [];
    decodes: ArrayBuffer[] = [];
    static decodeRejects = false;

    constructor() {
        FakeContext.made.push(this);
    }

    resume(): Promise<void> {
        this.resumes += 1;
        if (FakeContext.resumeRejects) return Promise.reject(new Error("blocked"));
        this.state = "running";
        return Promise.resolve();
    }

    createGain(): FakeNode {
        return this.track(this.gains);
    }

    createDynamicsCompressor(): FakeNode {
        return this.track(this.compressors);
    }

    createWaveShaper(): FakeNode {
        return this.track(this.shapers);
    }

    createBufferSource(): FakeNode {
        return this.track(this.sources);
    }

    createOscillator(): FakeNode {
        return this.track(this.oscillators);
    }

    createBiquadFilter(): FakeNode {
        return this.track(this.filters);
    }

    decodeAudioData(bytes: ArrayBuffer): Promise<{ decodedFrom: ArrayBuffer }> {
        this.decodes.push(bytes);
        if (FakeContext.decodeRejects) return Promise.reject(new Error("undecodable"));
        return Promise.resolve({ decodedFrom: bytes });
    }

    createBuffer(_channels: number, length: number): { getChannelData: () => Float32Array } {
        const samples = new Float32Array(length);
        this.buffers.push({ samples });
        return { getChannelData: () => samples };
    }

    private track(list: FakeNode[]): FakeNode {
        const node = new FakeNode();
        list.push(node);
        return node;
    }
}

interface FakePage {
    environment: AudioEnvironment;
    document: { hidden: boolean };
    audioSession: { type: string } | undefined;
    fetched: string[];
    fetchRejects: boolean;
}

function pageWith(contextClass: unknown = FakeContext): FakePage {
    const document = { hidden: false };
    const audioSession = { type: "auto" };
    const page: FakePage = {
        environment: {
            AudioContext: contextClass as AudioEnvironment["AudioContext"],
            navigator: { audioSession },
            document,
            fetch: (url) => {
                page.fetched.push(url);
                return page.fetchRejects
                    ? Promise.reject(new Error("offline"))
                    : Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(url.length)) });
            },
        },
        document,
        audioSession,
        fetched: [],
        fetchRejects: false,
    };
    return page;
}

function onlyContext(): FakeContext {
    return FakeContext.made[0] as FakeContext;
}

const TONE: Voice = {
    kind: "tone",
    wave: "triangle",
    at: 0.25,
    seconds: 0.5,
    frequency: 200,
    endFrequency: 100,
    gain: 0.4,
};
const NOISE: Voice = { kind: "noise", at: 0.5, seconds: 0.25, frequency: 3000, quality: 0.9, gain: 0.5 };

async function readyPort(page: FakePage = pageWith()) {
    const port = createWebAudioPort(page.environment);
    await port.resume();
    return port;
}

describe("the context", () => {
    beforeEachReset();

    it("is not made before the first resume", () => {
        createWebAudioPort(pageWith().environment);

        expect(FakeContext.made).toHaveLength(0);
    });

    it("is made once and later resumes only wake it", async () => {
        const port = await readyPort();
        onlyContext().state = "suspended";

        await port.resume();

        expect(FakeContext.made).toHaveLength(1);
        expect(onlyContext().resumes).toBe(2);
    });

    it("is not woken again while it runs", async () => {
        const port = await readyPort();

        await port.resume();

        expect(onlyContext().resumes).toBe(1);
    });

    it("wakes the phone's output with a silent sample", async () => {
        await readyPort();

        const [unlock] = onlyContext().sources;
        expect(unlock?.startedAt).toBe(0);
        expect(unlock?.connectedTo).toEqual([onlyContext().destination]);
    });

    it("holds the phone's silent switch", async () => {
        const page = pageWith();

        await readyPort(page);

        expect(page.audioSession?.type).toBe("ambient");
    });

    it("works in a browser without an audio session", async () => {
        const page = pageWith();
        page.audioSession = undefined;
        const environment = { ...page.environment, navigator: {} };

        const port = createWebAudioPort(environment);
        await port.resume();

        expect(port.ready(false)).toBe(true);
    });
});

describe("ready", () => {
    beforeEachReset();

    it("is false before the first resume", () => {
        expect(createWebAudioPort(pageWith().environment).ready(false)).toBe(false);
    });

    it("is true while the context runs and the page is visible", async () => {
        const port = await readyPort();

        expect(port.ready(false)).toBe(true);
    });

    it("is false while the page is hidden", async () => {
        const page = pageWith();
        const port = await readyPort(page);

        page.document.hidden = true;

        expect(port.ready(false)).toBe(false);
    });

    it("is true in a hidden page when the sound is asked for there", async () => {
        const page = pageWith();
        const port = await readyPort(page);

        page.document.hidden = true;

        expect(port.ready(true)).toBe(true);
    });

    it("is false once the context stops running", async () => {
        const port = await readyPort();

        onlyContext().state = "suspended";

        expect(port.ready(false)).toBe(false);
    });
});

describe("a browser that cannot make sound", () => {
    beforeEachReset();

    it("stays silent without an AudioContext", async () => {
        const environment = { navigator: {}, document: { hidden: false }, fetch: pageWith().environment.fetch };
        const port = createWebAudioPort(environment);

        await port.resume();

        expect(port.ready(false)).toBe(false);
    });

    it("stays silent when the resume is rejected", async () => {
        FakeContext.resumeRejects = true;
        const port = await readyPort();

        expect(port.ready(false)).toBe(false);
    });

    it("stays silent when the context cannot be made", async () => {
        function Refusing(): never {
            throw new Error("no device");
        }
        const port = await readyPort(pageWith(Refusing));

        expect(port.ready(false)).toBe(false);
    });

    it("stays silent when the audio session cannot be set", async () => {
        const page = pageWith();
        Object.defineProperty(page.audioSession, "type", {
            set() {
                throw new Error("locked");
            },
        });

        const port = await readyPort(page);

        expect(FakeContext.made).toHaveLength(0);
        expect(port.ready(false)).toBe(false);
    });
});

describe("the master", () => {
    beforeEachReset();

    it("runs through a limiter and a ceiling to the destination", async () => {
        await readyPort();
        const context = onlyContext();

        const [master] = context.gains;
        const [limiter] = context.compressors;
        const [ceiling] = context.shapers;
        expect(master?.connectedTo).toEqual([limiter]);
        expect(limiter?.connectedTo).toEqual([ceiling]);
        expect(ceiling?.connectedTo).toEqual([context.destination]);
    });

    it("shapes the ceiling with the curve the module owns, sample by sample", async () => {
        await readyPort();

        const [ceiling] = onlyContext().shapers;

        expect(ceiling?.curve).toEqual(ceilingCurve());
        expect(ceiling?.oversample).toBe("none");
    });

    it("limits hard from a level below full scale on, without lowering what stays under it", async () => {
        await readyPort();

        const [limiter] = onlyContext().compressors;

        expect(limiter?.threshold.value).toBeLessThan(0);
        expect(limiter?.knee.value).toBe(0);
        expect(limiter?.ratio.value).toBeGreaterThanOrEqual(10);
    });

    it("takes the loudness from the context's time on", async () => {
        const port = await readyPort();

        port.setLoudness(0.25);

        expect(onlyContext().gains[0]?.gain.sets).toEqual([{ value: 0.25, at: NOW }]);
    });
});

describe("the sea", () => {
    beforeEachReset();

    it("is not made before the first tap, whatever level is asked", () => {
        const port = createWebAudioPort(pageWith().environment);

        port.setSea(0.5);

        expect(FakeContext.made).toEqual([]);
    });

    it("is not made while it stays silent", async () => {
        const port = await readyPort();
        const woken = onlyContext().sources.length;

        port.setSea(0);

        expect(onlyContext().sources).toHaveLength(woken);
    });

    it("starts at the first level above silence as looped noise through the limiter's input", async () => {
        const port = await readyPort();

        port.setSea(0.4);

        const looped = onlyContext().sources.filter((source) => source.loop);
        expect(looped.length).toBeGreaterThan(0);
        const sea = onlyContext().gains.find((gain) => gain.gain.targets.length > 0);
        expect(sea?.connectedTo).toContain(onlyContext().compressors[0]);
    });

    it("fades to each level from the context's time on and is made once", async () => {
        const port = await readyPort();

        port.setSea(0.4);
        const sources = onlyContext().sources.length;
        port.setSea(0);

        const sea = onlyContext().gains.find((gain) => gain.gain.targets.length > 0);
        expect(sea?.gain.targets.map(({ value, at }) => ({ value, at }))).toEqual([
            { value: 0.4, at: NOW },
            { value: 0, at: NOW },
        ]);
        expect(sea?.gain.targets.every(({ timeConstant }) => timeConstant > 0)).toBe(true);
        expect(onlyContext().sources).toHaveLength(sources);
    });
});

describe("a voice", () => {
    beforeEachReset();

    it("starts at the context's time plus the lead and its own offset", async () => {
        const port = await readyPort();

        port.playVoice(TONE, 0.5);
        port.playVoice(NOISE, 0.5);

        expect(onlyContext().oscillators[0]?.startedAt).toBe(NOW + 0.5 + TONE.at);
        expect(onlyContext().sources[1]?.startedAt).toBe(NOW + 0.5 + NOISE.at);
    });

    it("stops after its length and a short tail", async () => {
        const port = await readyPort();

        port.playVoice(TONE, 0);

        const oscillator = onlyContext().oscillators[0] as FakeNode;
        expect(oscillator.stoppedAt).toBeGreaterThan(NOW + TONE.at + TONE.seconds);
    });

    it("plays a tone as its wave gliding to its end pitch", async () => {
        const port = await readyPort();

        port.playVoice(TONE, 0);

        const oscillator = onlyContext().oscillators[0] as FakeNode;
        expect(oscillator.type).toBe("triangle");
        expect(oscillator.frequency.sets[0]?.value).toBe(200);
        expect(oscillator.frequency.ramps[0]?.value).toBe(100);
    });

    it("keeps the pitch of a voice without an end pitch", async () => {
        const port = await readyPort();

        port.playVoice({ ...TONE, endFrequency: undefined }, 0);

        expect((onlyContext().oscillators[0] as FakeNode).frequency.ramps).toEqual([]);
    });

    it("plays a noise through a band around its frequency", async () => {
        const port = await readyPort();

        port.playVoice(NOISE, 0);

        const filter = onlyContext().filters[0] as FakeNode;
        expect(filter.type).toBe("bandpass");
        expect(filter.Q.value).toBe(0.9);
        expect(filter.frequency.sets[0]?.value).toBe(3000);
    });

    it("plays a noise from the shared noise buffer", async () => {
        const port = await readyPort();

        port.playVoice(NOISE, 0);

        const noise = onlyContext().sources[1] as FakeNode;
        const [shared] = onlyContext().buffers;
        expect(noise.buffer).toBeDefined();
        expect(shared?.samples.some((sample) => sample !== 0)).toBe(true);
    });

    it("rises to its gain and falls to silence", async () => {
        const port = await readyPort();

        port.playVoice(TONE, 0);

        const envelope = onlyContext().gains[1] as FakeNode;
        const [rise, fall] = envelope.gain.ramps;
        expect(rise?.value).toBe(0.4);
        expect(fall?.value).toBeLessThan(0.001);
        expect(fall?.at).toBeGreaterThan(rise?.at as number);
    });

    it("never asks the envelope for zero", async () => {
        const port = await readyPort();

        port.playVoice({ ...TONE, gain: 0 }, 0);

        expect((onlyContext().gains[1] as FakeNode).gain.ramps[0]?.value).toBeGreaterThan(0);
    });
});

function beforeEachReset(): void {
    beforeEach(() => {
        FakeContext.made = [];
        FakeContext.resumeRejects = false;
        FakeContext.decodeRejects = false;
    });
}

describe("recordings", () => {
    beforeEachReset();

    const ACHTZEHN = "/voice/achtzehn.mp3";
    const ZWANZIG = "/voice/zwanzig.mp3";

    it("are not fetched before the context is made", async () => {
        const page = pageWith();

        await createWebAudioPort(page.environment).loadRecordings([ACHTZEHN]);

        expect(page.fetched).toEqual([]);
    });

    it("are fetched once, however often they are asked for", async () => {
        const page = pageWith();
        const port = await readyPort(page);

        await Promise.all([port.loadRecordings([ACHTZEHN, ZWANZIG]), port.loadRecordings([ACHTZEHN])]);
        await port.loadRecordings([ACHTZEHN, ZWANZIG]);

        expect(page.fetched).toEqual([ACHTZEHN, ZWANZIG]);
        expect(onlyContext().decodes).toHaveLength(2);
    });

    it("play from the start of their buffer through the master gain, after the delay asked for", async () => {
        const port = await readyPort();
        await port.loadRecordings([ACHTZEHN]);
        const woken = onlyContext().sources.length;

        port.playRecording(ACHTZEHN, 0.25);

        const [source] = onlyContext().sources.slice(woken);
        expect(source?.buffer).toEqual({ decodedFrom: onlyContext().decodes[0] });
        expect(source?.startedAt).toBe(NOW + 0.25);
        expect(source?.connectedTo).toEqual([onlyContext().gains[0]]);
    });

    it("that are not loaded play nothing", async () => {
        const port = await readyPort();
        const woken = onlyContext().sources.length;

        port.playRecording(ACHTZEHN, 0);

        expect(onlyContext().sources).toHaveLength(woken);
    });

    it.each([
        { name: "that cannot be fetched", fetchRejects: true, decodeRejects: false },
        { name: "that cannot be decoded", fetchRejects: false, decodeRejects: true },
    ])("$name stay unloaded and are fetched again by the next call", async ({ fetchRejects, decodeRejects }) => {
        const page = pageWith();
        const port = await readyPort(page);
        page.fetchRejects = fetchRejects;
        FakeContext.decodeRejects = decodeRejects;
        const woken = onlyContext().sources.length;

        await port.loadRecordings([ACHTZEHN]);
        port.playRecording(ACHTZEHN, 0);
        await port.loadRecordings([ACHTZEHN]);

        expect(page.fetched).toEqual([ACHTZEHN, ACHTZEHN]);
        expect(onlyContext().sources).toHaveLength(woken);
    });
});

describe("the ceiling curve", () => {
    const curve = ceilingCurve();
    const ceiling = 10 ** (CEILING_DECIBELS / 20);
    const knee = 10 ** (LIMITER_THRESHOLD_DECIBELS / 20);
    const inputAt = (index: number): number => (2 * index) / (curve.length - 1) - 1;

    it("never passes full scale, and holds the level that its ceiling names", () => {
        expect(CEILING_DECIBELS).toBeLessThan(0);
        expect(Math.max(...curve.map(Math.abs))).toBeLessThanOrEqual(ceiling);
    });

    it("leaves everything under the limiter's threshold as it is", () => {
        curve.forEach((output, index) => {
            if (Math.abs(inputAt(index)) <= knee) expect(output).toBeCloseTo(inputAt(index), 5);
        });
    });

    it("rises with its input, so a louder sound is never made quieter", () => {
        curve.forEach((output, index) => {
            if (index > 0) expect(output).toBeGreaterThanOrEqual(curve[index - 1] as number);
        });
    });

    it("is odd, so it adds no offset", () => {
        expect(curve[Math.floor(curve.length / 2)]).toBe(0);
        expect(curve[0]).toBe(-(curve.at(-1) as number));
    });
});
