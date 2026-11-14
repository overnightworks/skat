import { vi } from "vitest";

/** Stands in for the browser a page's sound reads: an audio context that counts its starts, the tap listeners and the stored settings; a device that can vibrate passes its `vibrate`. */
export function stubBrowser(options: {
    reducedMotion: boolean;
    stored?: string;
    hidden?: boolean;
    vibrate?: (pattern: readonly number[]) => void;
}) {
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
        static readonly made: StubContext[] = [];
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
        createWaveShaper = node;
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
    const page = { hidden: options.hidden === true, documentElement: { lang: "" } };
    vi.stubGlobal("document", page);
    vi.stubGlobal("window", {
        fetch: vi.fn(() => Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(1)) })),
        AudioContext: StubContext,
        navigator: options.vibrate ? { vibrate: options.vibrate } : {},
        document: page,
        matchMedia: () => ({ matches: options.reducedMotion, addEventListener: vi.fn() }),
        localStorage: { getItem: () => options.stored ?? null },
        addEventListener: (type: string, handler: () => void) => listeners.set(type, handler),
        removeEventListener: (type: string) => listeners.delete(type),
    });
    const decodes = (): number => StubContext.made.reduce((all, one) => all + one.decodeAudioData.mock.calls.length, 0);
    return {
        started,
        listeners,
        decodes,
        masterLoudness: () => gains[0]?.setValueAtTime.mock.calls[0]?.[0] as number,
    };
}
