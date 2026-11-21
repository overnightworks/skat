import { describe, expect, it } from "vitest";
import { EVERY_HAND_DEALT, table as tableOfAHand } from "./cues.fixtures.ts";
import {
    BID_EIGHTEEN,
    FakePort,
    OWN_SEAT,
    PASS,
    soundAt,
    tableAwaitingAWord,
    tableSeenFrom,
} from "./tableSound.fixtures.ts";

describe("the tap of a „Weg“", () => {
    it("sounds as a bid's does while the auction still awaits a word, where both spring up in a bubble", () => {
        const [passed, bid] = [new FakePort(), new FakePort()];

        soundAt(passed).forCues([PASS], tableAwaitingAWord(OWN_SEAT));
        soundAt(bid).forCues([BID_EIGHTEEN], tableAwaitingAWord(OWN_SEAT));

        expect(passed.played.length).toBeGreaterThan(0);
        expect(passed.played).toEqual(bid.played);
    });

    it.each([
        { name: "the pass has ended the auction", table: tableOfAHand(2, EVERY_HAND_DEALT) },
        { name: "the table has no hand", table: tableSeenFrom(OWN_SEAT) },
    ])("is silent once $name, where no bubble shows it", ({ table }) => {
        const port = new FakePort();

        soundAt(port).forCues([PASS], table);

        expect(port.played).toEqual([]);
    });
});
