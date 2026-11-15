import type { Cue } from "./cues.ts";
import { language, type Key } from "./words.ts";

/** The catalog key of a spoken word; its recording is the file of that name in the page's language. */
export type VoiceKey = Extract<Key, `voice.${string}`>;

// The recordings are shipped beside the code as files of their own; a file is never inlined, since the port fetches it.
const RECORDINGS = import.meta.glob<string>("./voice/*/*.mp3", {
    query: "?url&no-inline",
    import: "default",
    eager: true,
});

// The lines a nudged chair grumbles; the next pick says the next line.
const GRUMBLES = [
    "voice.grumbleComing",
    "voice.grumbleRush",
    "voice.grumbleThinking",
] as const satisfies readonly VoiceKey[];

/** The line a nudged chair grumbles for the pick of its cue. */
export function grumbleOf(pick: number): VoiceKey {
    return GRUMBLES[pick % GRUMBLES.length] as VoiceKey;
}

/** The word the voice says for a cue, or nothing when the cue shows nothing a voice would repeat. */
export function voiceKeyOf(cue: Cue): VoiceKey | undefined {
    if (cue.kind === "nudged") return grumbleOf(cue.pick);
    if (cue.kind === "word-said") return `voice.${cue.said.word}`;
    if (cue.kind !== "bid-said") return undefined;
    // The server names a value with every bid and every hold.
    return cue.word.action === "pass" ? "voice.pass" : (`voice.value${String(cue.word.value)}` as VoiceKey);
}

/** Where the recording of a key lies in the page's language. */
export function recordingOf(key: VoiceKey): string | undefined {
    return RECORDINGS[`./voice/${language}/${key}.mp3`];
}

/** Every recording of the page's language. */
export function everyRecording(): string[] {
    return Object.entries(RECORDINGS)
        .filter(([path]) => path.startsWith(`./voice/${language}/`))
        .map(([, url]) => url);
}
