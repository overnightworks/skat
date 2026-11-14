import { describe, expect, it } from "vitest";
import { SOUND_SETS, type SoundMoment } from "./soundSets.ts";

const MOMENTS: SoundMoment[] = ["card-played", "bid-said", "word-said", "trick-swept"];
const LONGEST_SOUND_SECONDS = 0.6;
const LONGEST_SWEEP_SECONDS = 0.4;

describe.each(Object.values(SOUND_SETS))("the set $id", (set) => {
    it.each(MOMENTS)("sounds %s in under 600 ms", (moment) => {
        const voices = set.voices[moment](1);

        expect(voices.length).toBeGreaterThan(0);
        for (const voice of voices) expect(voice.at + voice.seconds).toBeLessThan(LONGEST_SOUND_SECONDS);
    });

    it("sounds the swept trick in under 400 ms", () => {
        for (const voice of set.voices["trick-swept"](1))
            expect(voice.at + voice.seconds).toBeLessThan(LONGEST_SWEEP_SECONDS);
    });

    it.each(MOMENTS)("sounds %s louder at a higher gain", (moment) => {
        const loudest = (gain: number): number => Math.max(...set.voices[moment](gain).map((voice) => voice.gain));

        expect(loudest(1)).toBeGreaterThan(loudest(0.5));
    });
});
