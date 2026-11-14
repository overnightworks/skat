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

const COMPRESSOR_THRESHOLD_DECIBELS = -14;
const COMPRESSOR_RATIO = 6;
const NOISE_SECONDS = 1.5;
const TONE_ATTACK_SECONDS = 0.004;
const NOISE_ATTACK_SECONDS = 0.003;
const TAIL_SECONDS = 0.05;
const ENVELOPE_FLOOR = 0.0001;
const GAIN_FLOOR = 0.0002;

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
        const compressor = context.createDynamicsCompressor();
        compressor.threshold.value = COMPRESSOR_THRESHOLD_DECIBELS;
        compressor.ratio.value = COMPRESSOR_RATIO;
        master.connect(compressor);
        compressor.connect(context.destination);
        return { context, master, noise: noiseBuffer(context) };
    }

    return {
        ready: () => graph?.context.state === "running" && !environment.document.hidden,
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
