import type { AudioPort, NoiseVoice, ToneVoice, Voice } from "./sound.ts";

declare global {
    // Safari and Chromium on the phone know the session; the DOM library of TypeScript does not.
    interface Navigator {
        audioSession?: { type: string };
    }
}

/** The parts of the browser window the port reads; an old browser leaves `AudioContext` out. */
export interface AudioEnvironment {
    readonly AudioContext?: new () => AudioContext;
    readonly navigator: Pick<Navigator, "audioSession">;
    readonly document: { readonly hidden: boolean };
    readonly fetch: (url: string) => Promise<Pick<Response, "arrayBuffer">>;
}

interface Graph {
    readonly context: AudioContext;
    readonly master: GainNode;
    readonly noise: AudioBuffer;
}

/** Above this level the limiter takes over; the sets play below it, so it acts on voices that land on top of each other. */
export const LIMITER_THRESHOLD_DECIBELS = -1;
/** Nothing leaves the graph above this level; sounds that start together can pass the limiter's attack by a little. */
export const CEILING_DECIBELS = -0.5;
const CEILING_STEPS = 4097;
const LIMITER_KNEE_DECIBELS = 0;
const LIMITER_RATIO = 20;
const LIMITER_ATTACK_SECONDS = 0.001;
const LIMITER_RELEASE_SECONDS = 0.1;
const NOISE_SECONDS = 1.5;
/** The envelope of a voice: a quick rise, an exponential fall, a tail before the source stops. The sets' loudness test renders by them. */
export const TONE_ATTACK_SECONDS = 0.004;
export const NOISE_ATTACK_SECONDS = 0.003;
export const TAIL_SECONDS = 0.05;
export const ENVELOPE_FLOOR = 0.0001;
export const GAIN_FLOOR = 0.0002;

const decibelsToGain = (decibels: number): number => 10 ** (decibels / 20);

/**
 * What the ceiling does to a sample between -1 and 1: it leaves what lies under the limiter's threshold alone and bends
 * what lies above it towards the ceiling, smoothly, so it never passes it. The shaper holds the curve's end for any
 * sample beyond it.
 */
export function ceilingCurve(): Float32Array<ArrayBuffer> {
    const knee = decibelsToGain(LIMITER_THRESHOLD_DECIBELS);
    const ceiling = decibelsToGain(CEILING_DECIBELS);
    return Float32Array.from({ length: CEILING_STEPS }, (_, index) => {
        const input = (2 * index) / (CEILING_STEPS - 1) - 1;
        const over = Math.abs(input) - knee;
        return over <= 0 ? input : Math.sign(input) * (knee + (ceiling - knee) * Math.tanh(over / (ceiling - knee)));
    });
}

/** Web Audio behind the port. The context is made inside the player's first gesture, since the browser keeps a context made earlier suspended. */
export function createWebAudioPort(environment: AudioEnvironment): AudioPort {
    let graph: Graph | undefined;
    const decoded = new Map<string, AudioBuffer>();
    const loading = new Set<string>();

    // A recording that fails to arrive or to decode stays unloaded and is fetched again by the next call.
    async function load(context: AudioContext, url: string): Promise<void> {
        try {
            const response = await environment.fetch(url);
            decoded.set(url, await context.decodeAudioData(await response.arrayBuffer()));
        } catch {
            // The voice is an extra; nothing on the page depends on it.
        } finally {
            loading.delete(url);
        }
    }

    function build(): Graph | undefined {
        if (environment.AudioContext === undefined) return undefined;
        // The phone's silent switch silences an ambient session.
        if (environment.navigator.audioSession) environment.navigator.audioSession.type = "ambient";
        const context = new environment.AudioContext();
        const master = context.createGain();
        const limiter = context.createDynamicsCompressor();
        limiter.threshold.value = LIMITER_THRESHOLD_DECIBELS;
        limiter.knee.value = LIMITER_KNEE_DECIBELS;
        limiter.ratio.value = LIMITER_RATIO;
        limiter.attack.value = LIMITER_ATTACK_SECONDS;
        limiter.release.value = LIMITER_RELEASE_SECONDS;
        const ceiling = context.createWaveShaper();
        ceiling.curve = ceilingCurve();
        // Oversampling would filter the shaped signal and let it overshoot the curve's end; sample by sample, nothing passes it.
        ceiling.oversample = "none";
        master.connect(limiter);
        limiter.connect(ceiling);
        ceiling.connect(context.destination);
        return { context, master, noise: noiseBuffer(context) };
    }

    return {
        ready: (whenHidden) => graph?.context.state === "running" && (whenHidden || !environment.document.hidden),
        async resume() {
            try {
                graph ??= build();
                if (graph === undefined || graph.context.state === "running") return;
                await graph.context.resume();
                unlockIos(graph.context);
            } catch {
                // A device that stays silent is not ready; nothing on the page depends on it.
            }
        },
        setLoudness(gain) {
            const { context, master } = graph as Graph;
            master.gain.setValueAtTime(gain, context.currentTime);
        },
        async loadRecordings(urls) {
            if (graph === undefined) return;
            const { context } = graph;
            const wanted = urls.filter((url) => !decoded.has(url) && !loading.has(url));
            for (const url of wanted) loading.add(url);
            await Promise.all(wanted.map((url) => load(context, url)));
        },
        playRecording(url, afterSeconds) {
            const buffer = decoded.get(url);
            if (buffer === undefined) return;
            const { context, master } = graph as Graph;
            const source = context.createBufferSource();
            source.buffer = buffer;
            source.connect(master);
            source.start(context.currentTime + afterSeconds);
        },
        playVoice(voice, afterSeconds) {
            const current = graph as Graph;
            const start = current.context.currentTime + afterSeconds + voice.at;
            if (voice.kind === "tone") startTone(current, voice, start);
            else startNoise(current, voice, start);
        },
    };
}

function noiseBuffer(context: AudioContext): AudioBuffer {
    const length = context.sampleRate * NOISE_SECONDS;
    const buffer = context.createBuffer(1, length, context.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let index = 0; index < length; index += 1) samples[index] = Math.random() * 2 - 1;
    return buffer;
}

// A silent sample played inside the gesture wakes iOS's output.
function unlockIos(context: AudioContext): void {
    const source = context.createBufferSource();
    source.buffer = context.createBuffer(1, 1, context.sampleRate);
    source.connect(context.destination);
    source.start();
}

function startTone({ context, master }: Graph, voice: ToneVoice, start: number): void {
    const oscillator = context.createOscillator();
    oscillator.type = voice.wave;
    glide(oscillator.frequency, voice, start, TONE_ATTACK_SECONDS);
    oscillator.connect(envelope(context, voice, start, TONE_ATTACK_SECONDS)).connect(master);
    oscillator.start(start);
    oscillator.stop(start + TONE_ATTACK_SECONDS + voice.seconds + TAIL_SECONDS);
}

function startNoise({ context, master, noise }: Graph, voice: NoiseVoice, start: number): void {
    const source = context.createBufferSource();
    source.buffer = noise;
    const filter = context.createBiquadFilter();
    filter.type = "bandpass";
    filter.Q.value = voice.quality;
    glide(filter.frequency, voice, start, NOISE_ATTACK_SECONDS);
    source
        .connect(filter)
        .connect(envelope(context, voice, start, NOISE_ATTACK_SECONDS))
        .connect(master);
    source.start(start);
    source.stop(start + NOISE_ATTACK_SECONDS + voice.seconds + TAIL_SECONDS);
}

function glide(parameter: AudioParam, voice: Voice, start: number, attack: number): void {
    parameter.setValueAtTime(voice.frequency, start);
    if (voice.endFrequency !== undefined)
        parameter.exponentialRampToValueAtTime(voice.endFrequency, start + attack + voice.seconds);
}

// A quick rise to the voice's level and an exponential fall to silence.
function envelope(context: AudioContext, voice: Voice, start: number, attack: number): GainNode {
    const node = context.createGain();
    node.gain.setValueAtTime(ENVELOPE_FLOOR, start);
    node.gain.exponentialRampToValueAtTime(Math.max(voice.gain, GAIN_FLOOR), start + attack);
    node.gain.exponentialRampToValueAtTime(ENVELOPE_FLOOR, start + attack + voice.seconds);
    return node;
}
