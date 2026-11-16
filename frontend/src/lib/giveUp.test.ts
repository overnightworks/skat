import { afterEach, describe, expect, it, vi } from "vitest";
import {
    answerGiveUp,
    giveUp,
    giveUpAsk,
    giveUpOffered,
    giveUpView,
    openCardsMark,
    playOpen,
    playOpenKey,
    requestEndedNotice,
    shorten,
    shortenKey,
} from "#lib/giveUp.ts";
import type { Cue } from "#lib/cues.ts";
import { TABLE_ID } from "#lib/table.fixtures.ts";
import { words } from "#lib/words.ts";
import {
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_PLAY_OPEN_SUFFIX,
    TABLE_SHORTEN_SUFFIX,
    TABLES_PATH,
} from "#lib/wire.ts";
import type { GiveUp, Shortening } from "../routes/(start)/tables.ts";
import { DECLARER, FIRST_OPPONENT, SECOND_OPPONENT, WATCHER, tableWith } from "#lib/giveUp.fixtures.ts";

const DECLARER_ASKS: GiveUp = { asking_seat: DECLARER, declined_seat: null };
const ONE_NO: GiveUp = { asking_seat: DECLARER, declined_seat: SECOND_OPPONENT };
const OPPONENT_ASKS: GiveUp = { asking_seat: FIRST_OPPONENT, declined_seat: null };

describe("a give-up request on the table", () => {
    it("names the declarer who asks with his face and offers both answers to an opponent", () => {
        const view = giveUpView(tableWith(FIRST_OPPONENT, DECLARER_ASKS));

        expect(view).toEqual({
            line: "wants-to-give-up",
            text: words["table.wantsToGiveUp"]({ name: "player 2" }),
            faces: [{ seat: DECLARER, name: "player 2", initial: "p" }],
            answers: ["agree", "decline"],
            marks: new Map(),
            demand: null,
            waitsFor: null,
            cardsHeld: false,
        });
    });

    it.each([
        { viewer: SECOND_OPPONENT, answers: ["agree"] },
        { viewer: FIRST_OPPONENT, answers: ["agree", "decline"] },
    ])("keeps only the yes for the opponent who said no, as $viewer sees it", ({ viewer, answers }) => {
        expect(giveUpView(tableWith(viewer, ONE_NO))?.answers).toEqual(answers);
    });

    it.each([FIRST_OPPONENT, SECOND_OPPONENT, DECLARER, WATCHER])(
        "marks the chair that said no with a cross for everyone, as chair %i sees it",
        (viewer) => {
            expect(giveUpView(tableWith(viewer, ONE_NO))?.marks.get(SECOND_OPPONENT)).toBe("declined");
        },
    );

    it.each([
        {
            request: DECLARER_ASKS,
            names: ["player 1", "player 3"],
            listed: "player 1 und player 3",
            marks: [
                [1, "unanswered"],
                [3, "unanswered"],
            ],
        },
        {
            request: ONE_NO,
            names: ["player 1"],
            listed: "player 1",
            marks: [
                [1, "unanswered"],
                [3, "declined"],
            ],
        },
    ] as const)("makes the asker wait for those who have not said no", ({ request, names, listed, marks }) => {
        const view = giveUpView(tableWith(DECLARER, request));

        expect(view).toMatchObject({
            line: "waits",
            text: words["table.waitingFor"]({ names: listed }),
            answers: [],
            cardsHeld: false,
        });
        expect(view?.faces.map((face) => face.name)).toEqual(names);
        expect(view?.marks).toEqual(new Map(marks));
    });

    it("shows a watcher the plaque and the cross and no answer", () => {
        expect(giveUpView(tableWith(WATCHER, ONE_NO))).toMatchObject({
            line: "wants-to-give-up",
            answers: [],
            marks: new Map([[SECOND_OPPONENT, "declined"]]),
        });
    });

    it("lets the partner answer an opponent's request and holds every card meanwhile", () => {
        expect(giveUpView(tableWith(SECOND_OPPONENT, OPPONENT_ASKS))).toMatchObject({
            line: "gives-up",
            text: words["table.wantsToGiveUp"]({ name: "player 1" }),
            answers: ["agree", "decline"],
            cardsHeld: true,
        });
    });

    it("makes the opponent who asked wait for his partner", () => {
        expect(giveUpView(tableWith(FIRST_OPPONENT, OPPONENT_ASKS))).toMatchObject({
            line: "waits",
            text: words["table.waitingFor"]({ names: "player 3" }),
            answers: [],
            marks: new Map([[SECOND_OPPONENT, "unanswered"]]),
            cardsHeld: true,
        });
    });

    it("offers the declarer no answer to an opponent's request", () => {
        expect(giveUpView(tableWith(DECLARER, OPPONENT_ASKS))).toMatchObject({ line: "gives-up", answers: [] });
    });

    it.each([
        { name: "nothing is asked", table: tableWith(DECLARER, null) },
        { name: "a chair is open", table: tableWith(FIRST_OPPONENT, DECLARER_ASKS, { waiting: 3 }) },
        { name: "the hand is a Ramsch", table: tableWith(FIRST_OPPONENT, DECLARER_ASKS, { ramsch: true }) },
    ])("draws no request when $name", ({ table }) => {
        expect(giveUpView(table)).toBeNull();
    });
});

describe("the plaque's drawing of a give-up request", () => {
    it("gives the opponent the stage's yes and the glass play-on button", () => {
        const view = giveUpView(tableWith(FIRST_OPPONENT, DECLARER_ASKS)) as NonNullable<ReturnType<typeof giveUpView>>;

        expect(giveUpAsk(view)).toEqual({
            text: words["table.wantsToGiveUp"]({ name: "player 2" }),
            faces: view.faces,
            waits: false,
            demand: null,
            waitsFor: null,
            buttons: [
                { answer: "agree", word: words["table.accept"], icon: "check", primary: true },
                { answer: "decline", word: words["table.playOn"], icon: "play", primary: false },
            ],
        });
    });

    it("carries the level a shortening demands as the plaque's demand line", () => {
        const view = giveUpView(tableWith(FIRST_OPPONENT, null, { shortening: SHORTENS_WITH_LEVEL })) as NonNullable<
            ReturnType<typeof giveUpView>
        >;

        expect(giveUpAsk(view).demand).toEqual(words["table.demands"]({ level: words["result.levelSchneider"] }));
    });

    it("waits with no button for the asker", () => {
        const view = giveUpView(tableWith(DECLARER, DECLARER_ASKS)) as NonNullable<ReturnType<typeof giveUpView>>;

        expect(giveUpAsk(view)).toMatchObject({ waits: true, buttons: [] });
    });
});

describe("the give-up row in the table menu", () => {
    it.each([FIRST_OPPONENT, DECLARER, SECOND_OPPONENT])("is offered to the seated person on chair %i", (viewer) => {
        expect(giveUpOffered(tableWith(viewer, null))).toBe(true);
    });

    it("stays while a request stands, so a repeated tap is the table's to refuse", () => {
        expect(giveUpOffered(tableWith(FIRST_OPPONENT, DECLARER_ASKS))).toBe(true);
    });

    it("is offered while Kontra is offered and while the first card waits for a word", () => {
        const owing = tableWith(FIRST_OPPONENT, null, { kontraWord: "kontra", owedBy: SECOND_OPPONENT });

        expect([
            giveUpOffered(tableWith(FIRST_OPPONENT, null, { kontraWord: "kontra" })),
            giveUpOffered(owing),
        ]).toEqual([true, true]);
    });

    it("is offered for a Grand Hand declared in the Ramsch stage", () => {
        expect(giveUpOffered(tableWith(FIRST_OPPONENT, null, { grandHandInRamsch: true }))).toBe(true);
    });

    it.each([
        { name: "a watcher looks on", table: tableWith(WATCHER, null) },
        { name: "a chair is open", table: tableWith(FIRST_OPPONENT, null, { waiting: 3 }) },
        { name: "the hand is a Ramsch", table: tableWith(FIRST_OPPONENT, null, { ramsch: true }) },
        { name: "no hand is dealt", table: { ...tableWith(FIRST_OPPONENT, null), hand: null } },
    ])("is missing when $name", ({ table }) => {
        expect(giveUpOffered(table)).toBe(false);
    });
});

describe("the notice that the opponents play on", () => {
    it("names both opponents once, in one sentence, and draws both faces", () => {
        const cues: Cue[] = [{ kind: "give-up-refused", seats: [FIRST_OPPONENT, SECOND_OPPONENT] }];

        expect(requestEndedNotice(cues, tableWith(DECLARER, null).chairs)).toEqual({
            text: words["table.playingOn"]({ names: "player 1 und player 3" }),
            initials: ["p", "p"],
            seat: null,
            occupied: false,
        });
    });
});

const SHORTENS: Shortening = { asking_seat: DECLARER, claim: "none", agreed_seat: null };
const SHORTENS_WITH_LEVEL: Shortening = { asking_seat: DECLARER, claim: "schneider", agreed_seat: null };
const SECOND_OPPONENT_AGREED: Shortening = { ...SHORTENS_WITH_LEVEL, agreed_seat: SECOND_OPPONENT };

describe("a shortening on the table", () => {
    it("names the declarer with his face and the level he demands, and offers an opponent yes and no", () => {
        const view = giveUpView(tableWith(FIRST_OPPONENT, null, { shortening: SHORTENS_WITH_LEVEL }));

        expect(view).toMatchObject({
            line: "wants-to-shorten",
            text: words["table.wantsToShorten"]({ name: "player 2" }),
            faces: [{ seat: DECLARER, name: "player 2", initial: "p" }],
            answers: ["agree", "decline"],
            demand: words["result.levelSchneider"],
            marks: new Map(),
            cardsHeld: false,
        });
    });

    it("leaves out the level line when none is demanded", () => {
        expect(giveUpView(tableWith(FIRST_OPPONENT, null, { shortening: SHORTENS }))?.demand).toBeNull();
    });

    it("draws the answers as a tick with Ja and a cross with Nein", () => {
        const view = giveUpView(tableWith(FIRST_OPPONENT, null, { shortening: SHORTENS })) as NonNullable<
            ReturnType<typeof giveUpView>
        >;

        expect(giveUpAsk(view).buttons).toEqual([
            { answer: "agree", word: words["table.yes"], icon: "check", primary: true },
            { answer: "decline", word: words["table.no"], icon: "cross", primary: false },
        ]);
    });

    it("keeps only the no for the opponent who said yes, and shows his yes to everyone", () => {
        const first = giveUpView(tableWith(SECOND_OPPONENT, null, { shortening: SECOND_OPPONENT_AGREED }));

        expect(first?.answers).toEqual(["decline"]);
        expect(first?.marks).toEqual(new Map([[SECOND_OPPONENT, "agreed"]]));
    });

    it("makes the declarer wait for the opponent who has not said yes", () => {
        const view = giveUpView(tableWith(DECLARER, null, { shortening: SECOND_OPPONENT_AGREED }));

        expect(view).toMatchObject({
            line: "waits",
            text: words["table.waitingFor"]({ names: "player 1" }),
            answers: [],
            demand: words["result.levelSchneider"],
            cardsHeld: false,
        });
        expect(view?.marks).toEqual(
            new Map([
                [FIRST_OPPONENT, "unanswered"],
                [SECOND_OPPONENT, "agreed"],
            ]),
        );
    });

    it("shows a watcher who said yes and who owes his answer, with no button", () => {
        const view = giveUpView(tableWith(WATCHER, null, { shortening: SECOND_OPPONENT_AGREED }));

        expect(view).toMatchObject({ line: "wants-to-shorten", answers: [] });
        expect(view?.marks).toEqual(
            new Map([
                [FIRST_OPPONENT, "unanswered"],
                [SECOND_OPPONENT, "agreed"],
            ]),
        );
    });
});

describe("an opponent's wrong open play on the table", () => {
    it("lets the declarer accept or play on and holds every card meanwhile", () => {
        expect(giveUpView(tableWith(DECLARER, null, { openPlayBy: FIRST_OPPONENT }))).toMatchObject({
            line: "plays-open",
            text: words["table.playsOpen"]({ name: "player 1" }),
            faces: [{ seat: FIRST_OPPONENT, name: "player 1", initial: "p" }],
            answers: ["agree", "decline"],
            waitsFor: null,
            cardsHeld: true,
        });
    });

    it("tells the opponent who played open whom the table waits for", () => {
        const view = giveUpView(tableWith(FIRST_OPPONENT, null, { openPlayBy: FIRST_OPPONENT }));

        expect(view).toMatchObject({
            text: words["table.youPlayOpen"],
            answers: [],
            waitsFor: { text: words["table.waitingFor"]({ names: "player 2" }), faces: [{ seat: DECLARER }] },
            marks: new Map([[DECLARER, "unanswered"]]),
        });
    });

    it.each([WATCHER, SECOND_OPPONENT])("shows chair %i the plaque without a button or a second line", (viewer) => {
        expect(giveUpView(tableWith(viewer, null, { openPlayBy: FIRST_OPPONENT }))).toMatchObject({
            answers: [],
            waitsFor: null,
        });
    });
});

describe("the keys that shorten and play open", () => {
    it("offers the declarer Abkürzen and an opponent Offen spielen, each the other's none", () => {
        expect([
            [shortenKey(tableWith(DECLARER, null)), playOpenKey(tableWith(DECLARER, null))],
            [shortenKey(tableWith(FIRST_OPPONENT, null)), playOpenKey(tableWith(FIRST_OPPONENT, null))],
        ]).toEqual([
            [true, false],
            [false, true],
        ]);
    });

    it.each([
        { name: "a watcher looks on", table: tableWith(WATCHER, null) },
        { name: "a chair is open", table: tableWith(DECLARER, null, { waiting: 3 }) },
        { name: "the hand is a Ramsch", table: tableWith(FIRST_OPPONENT, null, { ramsch: true }) },
        { name: "a give-up stands", table: tableWith(DECLARER, OPPONENT_ASKS) },
        { name: "a shortening stands", table: tableWith(DECLARER, null, { shortening: SHORTENS }) },
        { name: "an open play waits", table: tableWith(FIRST_OPPONENT, null, { openPlayBy: SECOND_OPPONENT }) },
    ])("are both missing when $name", ({ table }) => {
        expect([shortenKey(table), playOpenKey(table)]).toEqual([false, false]);
    });

    it("offers Offen spielen while a Kontra word is offered, the rows living in the menu beside it", () => {
        expect(playOpenKey(tableWith(FIRST_OPPONENT, null, { kontraWord: "kontra" }))).toBe(true);
    });
});

describe("the notice that the game goes on", () => {
    it("is none when the update brought no end of a request", () => {
        expect(requestEndedNotice([{ kind: "auction-ended" }], tableWith(DECLARER, null).chairs)).toBeNull();
    });

    it.each([
        { kind: "shortening-refused", text: words["table.saidNoPlayingOn"]({ name: "player 3" }) },
        { kind: "open-play-on", text: words["table.playsOpenOn"]({ name: "player 3" }) },
    ] as const)("names the seat once with its face after $kind", ({ kind, text }) => {
        expect(requestEndedNotice([{ kind, seat: SECOND_OPPONENT }], tableWith(DECLARER, null).chairs)).toEqual({
            text,
            initials: ["p"],
            seat: null,
            occupied: false,
        });
    });
});

describe("the marks a chair keeps after a request", () => {
    const refused = { refusedBy: SECOND_OPPONENT };

    it("crosses the opponent whose no ended the shortening, for every viewer", () => {
        expect(
            [DECLARER, FIRST_OPPONENT, WATCHER].map((viewer) => openCardsMark(tableWith(viewer, null, refused), 3)),
        ).toEqual(["declined", "declined", "declined"]);
    });

    it("leaves the old cross off while a new shortening stands", () => {
        expect(
            openCardsMark(tableWith(DECLARER, null, { ...refused, shortening: SHORTENS }), SECOND_OPPONENT),
        ).toBeUndefined();
    });

    it("marks no chair while the table has no hand in play", () => {
        expect(openCardsMark({ ...tableWith(WATCHER, null), hand: null }, FIRST_OPPONENT)).toBeUndefined();
    });

    it("puts an eye on the chair whose cards lie open and none on the others", () => {
        const table = tableWith(WATCHER, null, { openHands: [{ seat: FIRST_OPPONENT, cards: [] }] });

        expect([DECLARER, FIRST_OPPONENT, SECOND_OPPONENT].map((seat) => openCardsMark(table, seat))).toEqual([
            undefined,
            "open",
            undefined,
        ]);
    });
});

describe("the requests that end a game early", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it.each([
        { name: "give up the game", ask: giveUp, suffix: TABLE_GIVE_UP_SUFFIX },
        { name: "shorten the game", ask: shorten, suffix: TABLE_SHORTEN_SUFFIX },
        { name: "play open", ask: playOpen, suffix: TABLE_PLAY_OPEN_SUFFIX },
    ])("send the version shown and a command id to $name", async ({ ask, suffix }) => {
        const table = tableWith(DECLARER, null);
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(table)));

        expect(await ask(TABLE_ID, 7, "command-5")).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-5", version: 7 });
    });

    it.each([
        { answer: "agree" as const, suffix: TABLE_GIVE_UP_AGREE_SUFFIX },
        { answer: "decline" as const, suffix: TABLE_GIVE_UP_DECLINE_SUFFIX },
    ])("sends the version shown and a command id to $answer a give-up", async ({ answer, suffix }) => {
        const table = tableWith(DECLARER, null);
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(table)));

        expect(await answerGiveUp(TABLE_ID, 7, "command-5", answer)).toEqual({ kind: "table", table });

        const [path, init] = vi.mocked(fetch).mock.calls[0] ?? [];
        expect(path).toBe(`${TABLES_PATH}/${TABLE_ID}${suffix}`);
        expect(JSON.parse((init as { body: string }).body)).toEqual({ command_id: "command-5", version: 7 });
    });
});
