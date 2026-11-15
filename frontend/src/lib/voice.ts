import type { BidWord, Cue } from "./cues.ts";
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

// The lines a chair says to hold a bid, instead of repeating its number.
const CONFIRMATIONS = [
    "voice.holdYes",
    "voice.holdSure",
    "voice.holdOfCourse",
    "voice.holdCertainly",
    "voice.holdHaveIt",
] as const satisfies readonly VoiceKey[];

// The one value the voice names two ways: as the number and as Null, whose lowest game is worth the same.
const NULL_BID = 23;
const NULL_BID_WORDS = ["voice.value23", "voice.null"] as const satisfies readonly VoiceKey[];

// The word of a bid or a hold: what every page of the table sees of it decides the pick, so every page says the same.
function bidWordKeyOf(seat: number, { action, value }: BidWord): VoiceKey {
    if (action === "pass") return "voice.pass";
    // The server names a value with every bid and every hold.
    const pick = seat + (value as number);
    if (action === "hold") return CONFIRMATIONS[pick % CONFIRMATIONS.length] as VoiceKey;
    return value === NULL_BID
        ? (NULL_BID_WORDS[pick % NULL_BID_WORDS.length] as VoiceKey)
        : (`voice.value${String(value)}` as VoiceKey);
}

/** The words the voice says for a cue in order, none when the cue shows nothing a voice would repeat. */
export function voiceKeysOf(cue: Cue): VoiceKey[] {
    switch (cue.kind) {
        case "nudged":
            return [grumbleOf(cue.pick)];
        case "word-said":
            return [`voice.${cue.said.word}`];
        case "game-announced":
            return announcementKeys(cue);
        case "bid-said":
            return [bidWordKeyOf(cue.seat, cue.word)];
        default:
            return [];
    }
}

// The game as the table's announcement reads it: the game, Ouvert, Hand and the announced Schneider or Schwarz. A suit or
// Grand ouvert game includes Hand, and an ouvert game has no announcement.
function announcementKeys({ game, hand, ouvert, announcement }: Extract<Cue, { kind: "game-announced" }>): VoiceKey[] {
    if (ouvert) return [`voice.${game}`, "voice.ouvert", ...(game === "null" && hand ? (["voice.hand"] as const) : [])];
    return [
        `voice.${game}`,
        ...(hand ? (["voice.hand"] as const) : []),
        ...(announcement === "none" ? [] : ([`voice.${announcement}`] as const)),
    ];
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
