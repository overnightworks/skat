import { describe, expect, it } from "vitest";
import { cuesBetween, isChairCue, springsUp, stampBetween, type Cue } from "#lib/cues.ts";
import { chairs as seatedChairs, LOST_GAME, ramschResult, table as tableWithResult } from "#lib/result.fixtures.ts";
import {
    auction,
    chairsWithCards,
    declaringAt,
    EVERY_HAND_DEALT,
    FOREHAND,
    MIDDLEHAND,
    playing,
    REARHAND,
    table,
} from "#lib/cues.fixtures.ts";
import { words } from "#lib/words.ts";
import type {
    AuctionWord,
    Card,
    Chair,
    GiveUp,
    Kontra,
    LastTrick,
    SeatedCard,
    Table,
} from "../routes/(start)/tables.ts";

const KREUZ_KING: Card = { suit: "kreuz", rank: "king" };
const KREUZ_ACE: Card = { suit: "kreuz", rank: "ace" };
const HERZ_NINE: Card = { suit: "herz", rank: "nine" };
const PIK_TEN: Card = { suit: "pik", rank: "ten" };
const KARO_SEVEN: Card = { suit: "karo", rank: "seven" };
const KARO_EIGHT: Card = { suit: "karo", rank: "eight" };
const KARO_JACK: Card = { suit: "karo", rank: "jack" };

const FIRST_TRICK_LAST = {
    cards: [KREUZ_KING, HERZ_NINE, KREUZ_ACE],
    leader_seat: FOREHAND,
    taker_seat: MIDDLEHAND,
};

describe("the cards laid between two versions of a table", () => {
    it.each([
        {
            name: "a lead the page sees is the one card laid",
            previous: table(1, EVERY_HAND_DEALT, { current: [] }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            laid: [{ seat: FOREHAND, card: KREUZ_KING }],
        },
        {
            name: "a card that joins the trick is the one card laid",
            previous: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            next: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            laid: [{ seat: MIDDLEHAND, card: HERZ_NINE }],
        },
        {
            name: "the card that completes a trick is laid and the trick stays on the felt",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 9, 9], { current: [], last: FIRST_TRICK_LAST }),
            laid: [{ seat: REARHAND, card: KREUZ_ACE }],
            completes: FIRST_TRICK_LAST,
        },
        {
            name: "the completing card and then the lead are laid, in that order, when both arrive together",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 8, 9], {
                current: [{ seat: MIDDLEHAND, card: PIK_TEN }],
                last: { ...FIRST_TRICK_LAST, taker_seat: MIDDLEHAND },
            }),
            laid: [
                { seat: REARHAND, card: KREUZ_ACE },
                { seat: MIDDLEHAND, card: PIK_TEN },
            ],
            completes: { ...FIRST_TRICK_LAST, taker_seat: MIDDLEHAND },
        },
    ] satisfies { name: string; previous: Table; next: Table; laid: SeatedCard[]; completes?: LastTrick }[])(
        "$name",
        ({ previous, next, laid, completes }) => {
            const played = laid.map(({ seat, card }): Cue => ({ kind: "card-played", seat, card }));
            const taken: Cue[] = completes === undefined ? [] : [{ kind: "trick-taken", trick: completes }];

            // The finished trick is named right after the card that finished it, before any lead.
            expect(cuesBetween(previous, next)).toEqual([...played.slice(0, 1), ...taken, ...played.slice(1)]);
        },
    );

    it.each([
        {
            name: "two completed tricks that the page skipped lay nothing",
            previous: table(3, [8, 8, 8], { current: [], last: FIRST_TRICK_LAST }),
            next: table(5, [7, 7, 7], { current: [], last: { ...FIRST_TRICK_LAST, leader_seat: REARHAND } }),
        },
        {
            name: "the first lead of a new deal lays nothing",
            previous: table(4, [7, 7, 7], { current: [], last: FIRST_TRICK_LAST }),
            next: table(5, EVERY_HAND_DEALT, { current: [{ seat: FOREHAND, card: KARO_SEVEN }] }),
        },
        {
            name: "a change the hands do not explain lays nothing",
            previous: table(1, EVERY_HAND_DEALT, { current: [] }),
            next: table(2, EVERY_HAND_DEALT, { current: [{ seat: FOREHAND, card: KARO_EIGHT }] }),
        },
        {
            name: "a change that takes a card from a hand without laying it lays nothing",
            previous: table(1, EVERY_HAND_DEALT, { current: [] }),
            next: table(2, [9, 10, 10], { current: [] }),
        },
        {
            name: "an update that changes no card lays nothing",
            previous: table(1, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_JACK }] }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_JACK }] }),
        },
        {
            name: "a card swapped for another on the felt lays nothing",
            previous: table(1, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: HERZ_NINE }] }),
        },
        {
            name: "a trick that completes from one card on the felt lays nothing",
            previous: table(3, [9, 10, 10], { current: [{ seat: FOREHAND, card: KREUZ_KING }] }),
            next: table(4, [9, 10, 9], { current: [], last: { ...FIRST_TRICK_LAST, cards: [KREUZ_KING, HERZ_NINE] } }),
        },
        {
            name: "a trick that completes without the cards on the felt lays nothing",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 9, 9], {
                current: [],
                last: { ...FIRST_TRICK_LAST, cards: [HERZ_NINE, KREUZ_KING, KREUZ_ACE] },
            }),
        },
        {
            name: "a trick that completes with no card added lays nothing",
            previous: table(3, [9, 9, 10], {
                current: [
                    { seat: FOREHAND, card: KREUZ_KING },
                    { seat: MIDDLEHAND, card: HERZ_NINE },
                ],
            }),
            next: table(4, [9, 9, 10], { current: [], last: { ...FIRST_TRICK_LAST, cards: [KREUZ_KING, HERZ_NINE] } }),
        },
        {
            name: "a table with no playing before lays nothing",
            previous: table(1, EVERY_HAND_DEALT, { declaring: declaringAt("discarding") }),
            next: table(2, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_SEVEN }] }),
        },
    ] satisfies { name: string; previous: Table; next: Table }[])("$name", ({ previous, next }) => {
        expect(cuesBetween(previous, next)).toEqual([]);
    });

    it("lays nothing for a table that is not newer than the one before it", () => {
        const previous = table(4, [9, 10, 10], { current: [{ seat: FOREHAND, card: KARO_JACK }] });
        const sameVersion = table(4, [9, 9, 10], {
            current: [
                { seat: FOREHAND, card: KARO_JACK },
                { seat: MIDDLEHAND, card: KARO_SEVEN },
            ],
        });

        expect(cuesBetween(previous, sameVersion)).toEqual([]);
    });

    it("lays nothing on the first table of a page", () => {
        const first = table(4, [9, 9, 10], {
            current: [
                { seat: FOREHAND, card: KARO_JACK },
                { seat: MIDDLEHAND, card: KARO_SEVEN },
            ],
        });

        expect(cuesBetween(undefined, first)).toEqual([]);
    });
});

describe("the moment the auction ended", () => {
    const running = table(1, EVERY_HAND_DEALT, { declaring: null, current: undefined });
    const choosing = table(2, EVERY_HAND_DEALT, { declaring: declaringAt("choosing"), current: undefined });
    const ended: Cue = { kind: "auction-ended" };

    it("is the update that brings the declaring after a hand without one", () => {
        expect(cuesBetween(running, choosing)).toEqual([ended]);
    });

    it.each([
        { name: "the first answer of the page", previous: undefined, next: choosing },
        {
            name: "an update inside the declaring",
            previous: choosing,
            next: table(3, EVERY_HAND_DEALT, { declaring: declaringAt("discarding"), current: undefined }),
        },
        {
            name: "an update while the auction runs",
            previous: running,
            next: table(2, EVERY_HAND_DEALT, { declaring: null, current: undefined }),
        },
        { name: "a table with no hand yet", previous: { ...running, hand: null }, next: choosing },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "auction-ended")).toBe(false);
    });
});

describe("the moment both opponents refused a give-up", () => {
    // The declarer at MIDDLEHAND asked and FOREHAND said no; REARHAND's no clears the request.
    const firstNo: GiveUp = { asking_seat: MIDDLEHAND, declined_seat: FOREHAND };
    const standing = table(5, [8, 8, 8], { current: [], giveUp: firstNo });
    const refused: Cue = { kind: "give-up-refused", seats: [FOREHAND, REARHAND] };

    it("is the update that clears the declarer's request after the first no and changes nothing else", () => {
        expect(cuesBetween(standing, table(6, [8, 8, 8], { current: [] }))).toEqual([refused]);
    });

    it.each([
        {
            name: "the first no, which keeps the request",
            previous: table(4, [8, 8, 8], { current: [], giveUp: { asking_seat: MIDDLEHAND, declined_seat: null } }),
            next: standing,
        },
        {
            name: "a card of the declarer, which takes the request back",
            previous: standing,
            next: table(6, [8, 7, 8], { current: [{ seat: MIDDLEHAND, card: KARO_JACK }] }),
        },
        {
            name: "a yes, which ends the hand",
            previous: standing,
            next: { ...table(6, [8, 8, 8]), hand: null },
        },
        {
            name: "a chair that changed hands",
            previous: standing,
            next: {
                ...table(6, [8, 8, 8], { current: [] }),
                chairs: chairsWithCards([8, 8, 8]).map((chair) =>
                    chair.seat === REARHAND ? { ...chair, occupant_name: "newcomer" } : chair,
                ),
            },
        },
        {
            name: "the declarer's no to an opponent's request",
            previous: table(4, [8, 8, 8], { current: [], giveUp: { asking_seat: FOREHAND, declined_seat: null } }),
            next: table(5, [8, 8, 8], { current: [] }),
        },
        {
            name: "a reload or a reconnect, which knows no table before",
            previous: undefined,
            next: table(6, [8, 8, 8], { current: [] }),
        },
        {
            name: "an update that keeps the request",
            previous: standing,
            next: table(6, [8, 8, 8], { current: [], giveUp: firstNo }),
        },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "give-up-refused")).toBe(false);
    });
});

describe("the bid a chair said between two versions of a table", () => {
    const BID_EIGHTEEN: AuctionWord = { seat: MIDDLEHAND, action: "bid", value: 18 };
    const HOLD_EIGHTEEN: AuctionWord = { seat: REARHAND, action: "hold", value: 18 };
    const PASS: AuctionWord = { seat: FOREHAND, action: "pass", value: null };
    const auctionTable = (version: number, spoken: AuctionWord[]): Table =>
        table(version, EVERY_HAND_DEALT, { declaring: null, spoken });

    it.each([
        { name: "a bid", spoken: [BID_EIGHTEEN], cue: { seat: MIDDLEHAND, word: { action: "bid", value: 18 } } },
        {
            name: "a hold, with the standing bid it answered",
            spoken: [BID_EIGHTEEN, HOLD_EIGHTEEN],
            before: [BID_EIGHTEEN],
            cue: { seat: REARHAND, word: { action: "hold", value: 18 } },
        },
        {
            name: "a pass",
            spoken: [PASS, BID_EIGHTEEN],
            before: [BID_EIGHTEEN],
            cue: { seat: FOREHAND, word: { action: "pass", value: null } },
        },
        {
            name: "a raised bid of a chair that bid before",
            spoken: [{ ...BID_EIGHTEEN, value: 20 }],
            before: [BID_EIGHTEEN],
            cue: { seat: MIDDLEHAND, word: { action: "bid", value: 20 } },
        },
    ] satisfies { name: string; spoken: AuctionWord[]; before?: AuctionWord[]; cue: object }[])(
        "is $name",
        ({ spoken, before, cue }) => {
            expect(cuesBetween(auctionTable(1, before ?? []), auctionTable(2, spoken))).toEqual([
                { kind: "bid-said", ...cue },
            ]);
        },
    );

    it("is the last chair's word when several chairs said theirs at once", () => {
        const cues = cuesBetween(auctionTable(1, []), auctionTable(3, [PASS, BID_EIGHTEEN, HOLD_EIGHTEEN]));

        expect(cues).toEqual([{ kind: "bid-said", seat: REARHAND, word: { action: "hold", value: 18 } }]);
    });

    it.each([
        { name: "the first answer of the page", previous: undefined, next: auctionTable(2, [BID_EIGHTEEN]) },
        {
            name: "a table that is not newer",
            previous: auctionTable(2, []),
            next: auctionTable(2, [BID_EIGHTEEN]),
        },
        {
            name: "words that did not change",
            previous: auctionTable(1, [BID_EIGHTEEN]),
            next: auctionTable(2, [BID_EIGHTEEN]),
        },
        {
            name: "a hand with no words yet",
            previous: { ...auctionTable(1, []), hand: null },
            next: auctionTable(2, []),
        },
        {
            name: "a play, which shows nothing at the table",
            previous: auctionTable(1, []),
            next: auctionTable(2, [{ seat: FOREHAND, action: "play", value: 18 }]),
        },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "bid-said")).toBe(false);
    });
});

describe("the word of Kontra said between two versions of a table", () => {
    const SAID_KONTRA = { seat: FOREHAND, word: "kontra" } as const;
    const SAID_RE = { seat: MIDDLEHAND, word: "re" } as const;
    const kontra = (said: Kontra["said"]): Kontra => ({
        said,
        factor: 2 ** said.length,
        my_word: null,
        first_card_waits_on: [],
        first_card_declined: [],
    });
    const wordTable = (version: number, said: Kontra["said"] | null): Table =>
        table(version, EVERY_HAND_DEALT, { declaring: null, kontra: said === null ? null : kontra(said) });
    const stampOfFelix = {
        text: words["kontra.stamp"]({ word: words["kontra.kontra"] }),
        label: words["kontra.saidBy"]({ name: "player 1", word: words["kontra.kontra"] }),
        initial: "p",
        agent: false,
    };

    it("is the word the update brought", () => {
        expect(cuesBetween(wordTable(5, []), wordTable(6, [SAID_KONTRA]))).toEqual([
            { kind: "word-said", said: SAID_KONTRA },
        ]);
    });

    it("is the last of two words said at once", () => {
        expect(cuesBetween(wordTable(5, []), wordTable(7, [SAID_KONTRA, SAID_RE]))).toEqual([
            { kind: "word-said", said: SAID_RE },
        ]);
    });

    it.each([
        { name: "the same words again", previous: wordTable(5, [SAID_KONTRA]), next: wordTable(6, [SAID_KONTRA]) },
        { name: "words of another hand", previous: wordTable(5, [SAID_KONTRA, SAID_RE]), next: wordTable(6, []) },
        { name: "a table without Kontra", previous: wordTable(5, null), next: wordTable(6, null) },
        {
            name: "a hand that has just ended",
            previous: wordTable(5, [SAID_KONTRA]),
            next: { ...wordTable(6, []), hand: null },
        },
    ])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "word-said")).toBe(false);
    });

    it("stamps the word with its mark and the sayer's face", () => {
        expect(stampBetween(wordTable(5, []), wordTable(6, [SAID_KONTRA]))).toEqual(stampOfFelix);
    });

    it("stamps the last of two words said at once", () => {
        expect(stampBetween(wordTable(5, []), wordTable(7, [SAID_KONTRA, SAID_RE]))).toMatchObject({
            text: words["kontra.stamp"]({ word: words["kontra.re"] }),
            initial: "p",
        });
    });

    it("stamps a hand's first word, as the table before it had no hand", () => {
        expect(stampBetween({ ...wordTable(5, []), hand: null }, wordTable(6, [SAID_KONTRA]))).toEqual(stampOfFelix);
    });

    it("shows an agent's word with the agent's mark", () => {
        const agents = wordTable(6, [SAID_KONTRA]);
        (agents.chairs[0] as Chair).occupant_kind = "agent";

        expect(stampBetween(wordTable(5, []), agents)).toMatchObject({ agent: true });
    });

    it("has no initial for a chair that has since been left", () => {
        const left = wordTable(6, [SAID_KONTRA]);
        (left.chairs[0] as Chair).occupant_name = null;

        expect(stampBetween(wordTable(5, []), left)?.initial).toBe("");
    });

    it.each([
        { name: "a page that has no table before it", previous: undefined, next: wordTable(6, [SAID_KONTRA]) },
        { name: "a table that is not newer", previous: wordTable(6, []), next: wordTable(6, [SAID_KONTRA]) },
        { name: "the same words again", previous: wordTable(5, [SAID_KONTRA]), next: wordTable(6, [SAID_KONTRA]) },
    ])("stamps nothing for $name", ({ previous, next }) => {
        expect(stampBetween(previous, next)).toBeNull();
    });
});

describe("the bubble that springs up", () => {
    const said = { seat: 1, word: { action: "bid", value: 20 } } as const;

    it.each([
        { name: "the bid just said by its chair", said, seat: 1, bubble: { kind: "bid", value: 20 }, springs: true },
        { name: "no bid said", said: null, seat: 1, bubble: { kind: "bid", value: 20 }, springs: false },
        { name: "another chair's bid", said, seat: 2, bubble: { kind: "bid", value: 20 }, springs: false },
        { name: "an earlier bid of the chair", said, seat: 1, bubble: { kind: "bid", value: 18 }, springs: false },
        { name: "a hold at the value", said, seat: 1, bubble: { kind: "hold", value: 20 }, springs: false },
        { name: "a chair without a bubble", said, seat: 1, bubble: null, springs: false },
    ] as const)("is $springs for $name", ({ said: bid, seat, bubble, springs }) => {
        expect(springsUp(bid, seat, bubble)).toBe(springs);
    });
});

describe("the chairs that changed hands between two versions of a table", () => {
    const OPEN_SEAT = 3;

    function chairOf(seat: number, name: string | null, kind: Chair["occupant_kind"], mine = false): Chair {
        return {
            ...(chairsWithCards(EVERY_HAND_DEALT)[0] as Chair),
            seat,
            occupant_name: name,
            occupant_kind: name === null ? null : kind,
            is_mine: mine,
            hand: null,
        };
    }

    // A table at `version` whose running hand waits for a sitter at the open seat, or has every chair taken.
    function chairsTable(version: number, waits: boolean, ...chairs: Chair[]): Table {
        const base = table(version, EVERY_HAND_DEALT);
        return {
            ...base,
            chairs,
            hand: { ...(base.hand as NonNullable<Table["hand"]>), waiting_seat: waits ? OPEN_SEAT : null },
        };
    }

    const anna = chairOf(1, "Anna", "person");
    const felix = chairOf(2, "Felix", "person", true);
    const free = chairOf(OPEN_SEAT, null, null);
    const nova = chairOf(OPEN_SEAT, "Nova", "agent");
    const lena = chairOf(OPEN_SEAT, "Lena", "person");

    it.each([
        {
            name: "an agent sits on a chair that was free between hands",
            previous: chairsTable(1, false, anna, felix, free),
            next: chairsTable(2, false, anna, felix, nova),
            cue: { kind: "chair-taken", seat: OPEN_SEAT, name: "Nova", agent: true, mine: false, inHand: false },
        },
        {
            name: "a person sits on a chair that was free between hands",
            previous: chairsTable(1, false, anna, felix, free),
            next: chairsTable(2, false, anna, felix, lena),
            cue: { kind: "chair-taken", seat: OPEN_SEAT, name: "Lena", agent: false, mine: false, inHand: false },
        },
        {
            name: "a person takes the open chair of the running hand",
            previous: chairsTable(1, true, anna, felix, free),
            next: chairsTable(2, false, anna, felix, lena),
            cue: { kind: "chair-taken", seat: OPEN_SEAT, name: "Lena", agent: false, mine: false, inHand: true },
        },
        {
            name: "the viewer sits down herself",
            previous: chairsTable(1, false, anna, chairOf(2, null, null), lena),
            next: chairsTable(2, false, anna, felix, lena),
            cue: { kind: "chair-taken", seat: 2, name: "Felix", agent: false, mine: true, inHand: false },
        },
        {
            name: "a person stands up between hands",
            previous: chairsTable(1, false, anna, felix, lena),
            next: chairsTable(2, false, anna, felix, free),
            cue: { kind: "chair-stood", seat: OPEN_SEAT, name: "Lena", agent: false, mine: false },
        },
        {
            name: "an agent leaves between hands",
            previous: chairsTable(1, false, anna, felix, nova),
            next: chairsTable(2, false, anna, felix, free),
            cue: { kind: "chair-stood", seat: OPEN_SEAT, name: "Nova", agent: true, mine: false },
        },
        {
            name: "an agent leaves a chair of the running hand",
            previous: chairsTable(1, false, anna, felix, nova),
            next: chairsTable(2, true, anna, felix, free),
            cue: { kind: "chair-opened", seat: OPEN_SEAT, name: "Nova", agent: true, mine: false },
        },
        {
            name: "a person stands up from the running hand",
            previous: chairsTable(1, false, anna, felix, lena),
            next: chairsTable(2, true, anna, felix, free),
            cue: { kind: "chair-opened", seat: OPEN_SEAT, name: "Lena", agent: false, mine: false },
        },
        {
            name: "the viewer stands up from the running hand herself",
            previous: chairsTable(1, false, anna, felix, lena),
            next: chairsTable(2, true, anna, chairOf(2, null, null), lena),
            cue: { kind: "chair-opened", seat: 2, name: "Felix", agent: false, mine: true },
        },
    ] satisfies { name: string; previous: Table; next: Table; cue: Cue }[])(
        "brings $name as one chair cue",
        ({ previous, next, cue }) => {
            expect(cuesBetween(previous, next).filter(isChairCue)).toEqual([cue]);
        },
    );

    it.each([
        {
            name: "a page that has no table before it",
            previous: undefined,
            next: chairsTable(2, false, anna, felix, nova),
        },
        {
            name: "a table that is not newer",
            previous: chairsTable(2, false, anna, felix, free),
            next: chairsTable(2, false, anna, felix, nova),
        },
        {
            name: "chairs that stay as they were",
            previous: chairsTable(1, false, anna, felix, nova),
            next: chairsTable(2, false, anna, felix, nova),
        },
        {
            name: "a chair that stays open",
            previous: chairsTable(1, true, anna, felix, free),
            next: chairsTable(2, true, anna, felix, free),
        },
    ])("bring nothing for $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next)).toEqual([]);
    });
});

// The table of `table`, seen by the chair of `viewer`, whose hand is the stage the test names.
function viewedBy(
    viewer: number | null,
    shown: Table,
    version: number,
    hand: Partial<NonNullable<Table["hand"]>>,
): Table {
    return {
        ...shown,
        version,
        chairs: shown.chairs.map((chair) => ({ ...chair, is_mine: chair.seat === viewer })),
        hand: { ...(shown.hand as NonNullable<Table["hand"]>), ...hand },
    };
}

describe("the turn that came to the viewer", () => {
    const base = table(1, EVERY_HAND_DEALT, { declaring: null });
    const bidding = (version: number, turn: number | null, viewer: number | null = FOREHAND): Table =>
        viewedBy(viewer, base, version, {
            auction: { ...auction(), awaiting: "bid", turn_seat: turn },
            declaring: null,
            playing: null,
        });
    const trick = (version: number, turn: number, viewer: number | null = FOREHAND): Table =>
        viewedBy(viewer, base, version, {
            auction: auction(),
            declaring: declaringAt("declared"),
            playing: playing({ turn_seat: turn }),
        });
    const came: Cue = { kind: "turn-came" };

    it("is the update that puts the viewer on turn after another chair", () => {
        expect(cuesBetween(bidding(1, MIDDLEHAND), bidding(2, FOREHAND))).toContainEqual(came);
    });

    it("is the update that puts the viewer on turn in the play", () => {
        expect(cuesBetween(trick(1, MIDDLEHAND), trick(2, FOREHAND))).toContainEqual(came);
    });

    it("is the update that gives the viewer the choice of the game", () => {
        const choosing = viewedBy(FOREHAND, base, 2, {
            auction: auction(),
            declaring: { ...declaringAt("choosing"), declarer_seat: FOREHAND },
        });

        expect(cuesBetween(bidding(1, MIDDLEHAND), choosing)).toContainEqual(came);
    });

    it("is the update that puts the viewer on turn in the stage of a Ramsch", () => {
        const pushing = viewedBy(FOREHAND, base, 2, {
            auction: auction(),
            declaring: null,
            ramsch: true,
            pushing: { turn_seat: FOREHAND, stage: "choosing", moves: [], factor: 1, put_back_cards: [] },
        });

        expect(cuesBetween(bidding(1, MIDDLEHAND), pushing)).toContainEqual(came);
    });

    it("comes again when the viewer's turn moves on to the next phase of the hand", () => {
        expect(cuesBetween(bidding(1, FOREHAND), trick(2, FOREHAND))).toContainEqual(came);
    });

    it.each([
        {
            name: "an update that leaves the viewer on turn",
            previous: bidding(1, FOREHAND),
            next: bidding(2, FOREHAND),
        },
        { name: "the turn of another chair", previous: bidding(1, MIDDLEHAND), next: bidding(2, REARHAND) },
        {
            name: "an update that takes the turn from the viewer",
            previous: bidding(1, FOREHAND),
            next: bidding(2, MIDDLEHAND),
        },
        {
            name: "a watcher, who has no chair",
            previous: bidding(1, MIDDLEHAND, null),
            next: bidding(2, FOREHAND, null),
        },
        { name: "the first answer of the page", previous: undefined, next: bidding(2, FOREHAND) },
        { name: "an update that is not newer", previous: bidding(2, MIDDLEHAND), next: bidding(2, FOREHAND) },
        {
            name: "a hand that waits for a sitter",
            previous: bidding(1, MIDDLEHAND),
            next: viewedBy(FOREHAND, bidding(2, FOREHAND), 2, { waiting_seat: REARHAND }),
        },
        { name: "an auction that is over", previous: bidding(1, MIDDLEHAND), next: bidding(2, null) },
        {
            name: "a game that is declared and not yet played",
            previous: bidding(1, MIDDLEHAND),
            next: viewedBy(FOREHAND, base, 2, { auction: auction(), declaring: declaringAt("declared") }),
        },
        {
            name: "a table with no hand",
            previous: bidding(1, MIDDLEHAND),
            next: { ...bidding(2, FOREHAND), hand: null },
        },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "turn-came")).toBe(false);
    });
});

describe("the deal that a table update brought", () => {
    const hand = table(1, EVERY_HAND_DEALT, { declaring: null });
    const dealtBy = (version: number, dealer: number): Table => ({
        ...hand,
        version,
        hand: { ...(hand.hand as NonNullable<Table["hand"]>), dealer_seat: dealer },
    });
    const result = tableWithResult(1, {});

    it("is the update that brings a hand to a table that had none", () => {
        expect(cuesBetween({ ...result, version: 1 }, { ...hand, version: 2 })).toContainEqual({ kind: "dealt" });
    });

    it("is the update that brings a hand with another dealer than the hand before", () => {
        expect(cuesBetween(dealtBy(1, FOREHAND), dealtBy(2, MIDDLEHAND))).toContainEqual({ kind: "dealt" });
    });

    it.each([
        {
            name: "the first answer of the page, as after a reload or a dropped connection",
            previous: undefined,
            next: dealtBy(2, FOREHAND),
        },
        { name: "an update inside the same hand", previous: dealtBy(1, FOREHAND), next: dealtBy(2, FOREHAND) },
        { name: "an update that is not newer", previous: dealtBy(2, FOREHAND), next: dealtBy(2, MIDDLEHAND) },
        { name: "an update that ends the hand", previous: dealtBy(1, FOREHAND), next: { ...result, version: 2 } },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(cuesBetween(previous, next).some((cue) => cue.kind === "dealt")).toBe(false);
    });
});

describe("the result that just appeared", () => {
    const before = { ...tableWithResult(1, null), version: 8 };
    const after = (changes: Parameters<typeof tableWithResult>[1] = {}, mine = 1): Table => ({
        ...tableWithResult(mine, changes),
        version: 9,
    });
    const appeared = (previous: Table | undefined, next: Table) =>
        cuesBetween(previous, next).filter((cue) => cue.kind === "result-appeared");

    it("is the ordinal of a result that the update brings to a table that had none", () => {
        expect(appeared(before, after({ ordinal: 4 }))).toEqual([
            { kind: "result-appeared", ordinal: 4, won: false, counts: true },
        ]);
    });

    it("is the next ordinal when a result stands and the update brings another one", () => {
        const standing = { ...after({ ordinal: 4 }), version: 8 };

        expect(appeared(standing, after({ ordinal: 5 }))[0]).toMatchObject({ ordinal: 5 });
    });

    it("is won for a viewer on the winning side and lost for a viewer on the other", () => {
        expect(appeared(before, after({}, 2))[0]).toMatchObject({ won: true });
        expect(appeared(before, after(LOST_GAME, 2))[0]).toMatchObject({ won: false });
    });

    it("is the declarer's outcome for a watcher, who has no chair", () => {
        const watcher = { ...after({}), chairs: seatedChairs(0) };

        expect(appeared(before, watcher)[0]).toMatchObject({ won: true });
    });

    it("counts only when a seat gained something", () => {
        const nothing = after({ gains: [1, 2, 3].map((seat) => ({ seat, gain: 0, won: false })) });

        expect(appeared(before, nothing)[0]).toMatchObject({ counts: false });
    });

    it.each([
        { name: "the first table of a page, a reload or a late join", previous: undefined, next: after() },
        {
            name: "the same result standing, as when a Weiter mark arrives",
            previous: { ...after({ ordinal: 4 }), version: 8 },
            next: after({ ordinal: 4 }),
        },
        { name: "an update that is not newer than the one before", previous: { ...before, version: 9 }, next: after() },
        { name: "an update that brings no result", previous: before, next: after(null) },
        {
            name: "a Ramsch result",
            previous: before,
            next: { ...after(null), result: ramschResult([14, 86, 20], [0, -86, 0], {}) },
        },
    ] satisfies { name: string; previous: Table | undefined; next: Table }[])("is not $name", ({ previous, next }) => {
        expect(appeared(previous, next)).toEqual([]);
    });
});
