import { describe, expect, it } from "vitest";
import { giveUpAsk, giveUpKey, giveUpView } from "#lib/giveUp.ts";
import { words } from "#lib/words.ts";
import type { GiveUp } from "../routes/(start)/tables.ts";
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

    it("lets the declarer answer an opponent's request and holds every card meanwhile", () => {
        expect(giveUpView(tableWith(DECLARER, OPPONENT_ASKS))).toMatchObject({
            line: "gives-up",
            text: words["table.givesUp"]({ name: "player 1" }),
            answers: ["agree", "decline"],
            cardsHeld: true,
        });
    });

    it("makes the opponent who asked wait for the declarer", () => {
        expect(giveUpView(tableWith(FIRST_OPPONENT, OPPONENT_ASKS))).toMatchObject({
            line: "waits",
            text: words["table.waitingFor"]({ names: "player 2" }),
            answers: [],
            marks: new Map([[DECLARER, "unanswered"]]),
            cardsHeld: true,
        });
    });

    it("offers the other opponent no answer to an opponent's request", () => {
        expect(giveUpView(tableWith(SECOND_OPPONENT, OPPONENT_ASKS))?.answers).toEqual([]);
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
            buttons: [
                { answer: "agree", word: words["table.accept"], icon: "check", primary: true },
                { answer: "decline", word: words["table.playOn"], icon: "play", primary: false },
            ],
        });
    });

    it("waits with no button for the asker", () => {
        const view = giveUpView(tableWith(DECLARER, DECLARER_ASKS)) as NonNullable<ReturnType<typeof giveUpView>>;

        expect(giveUpAsk(view)).toMatchObject({ waits: true, buttons: [] });
    });
});

describe("the give-up key on the table bar", () => {
    it.each([FIRST_OPPONENT, DECLARER, SECOND_OPPONENT])("is offered to the seated person on chair %i", (viewer) => {
        expect(giveUpKey(tableWith(viewer, null))).toEqual({ round: false });
    });

    it("stays while a request stands, so a repeated tap is the table's to refuse", () => {
        expect(giveUpKey(tableWith(FIRST_OPPONENT, DECLARER_ASKS))).toEqual({ round: false });
    });

    it("goes round while Kontra is offered", () => {
        expect(giveUpKey(tableWith(FIRST_OPPONENT, null, { kontraWord: "kontra" }))).toEqual({ round: true });
    });

    it("is offered for a Grand Hand declared in the Ramsch stage", () => {
        expect(giveUpKey(tableWith(FIRST_OPPONENT, null, { grandHandInRamsch: true }))).toEqual({ round: false });
    });

    it.each([
        { name: "a watcher looks on", table: tableWith(WATCHER, null) },
        { name: "a chair is open", table: tableWith(FIRST_OPPONENT, null, { waiting: 3 }) },
        { name: "the hand is a Ramsch", table: tableWith(FIRST_OPPONENT, null, { ramsch: true }) },
        { name: "no hand is dealt", table: { ...tableWith(FIRST_OPPONENT, null), hand: null } },
    ])("is missing when $name", ({ table }) => {
        expect(giveUpKey(table)).toBeNull();
    });
});
