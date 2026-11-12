import { describe, expect, it } from "vitest";
import { giveUpView } from "#lib/giveUp.ts";
import { words } from "#lib/words.ts";
import type { Chair, GiveUp, Table } from "../routes/(start)/tables.ts";

const DECLARER = 2;
const FIRST_OPPONENT = 1;
const SECOND_OPPONENT = 3;
const WATCHER = 0;
const AND = ` ${words["result.and"]} `;

function chairs(mine: number): Chair[] {
    return [1, 2, 3].map((seat) => ({
        seat,
        occupant_name: `player ${String(seat)}`,
        occupant_kind: "person",
        is_mine: seat === mine,
        is_away: false,
        ready: false,
        total: null,
        hand: { position: "forehand", card_count: 9 },
    }));
}

// A declared game in play at which `request` stands, seen by the chair `mine` (0 is a watcher's).
function tableWith(mine: number, request: GiveUp | null, changes: { waiting?: number; ramsch?: boolean } = {}): Table {
    return {
        id: "a".repeat(32),
        version: 7,
        chairs: chairs(mine),
        watchers: 0,
        result: null,
        passed_in: null,
        ended: null,
        hand: {
            dealer_seat: 3,
            own_cards: [],
            skat_count: 2,
            waiting_seat: changes.waiting ?? null,
            auction: {
                turn_seat: null,
                facing_seat: null,
                awaiting: null,
                standing: null,
                values: [],
                words: [],
                declared: null,
            },
            declaring: changes.ramsch
                ? null
                : {
                      declarer_seat: DECLARER,
                      stage: "declared",
                      declaration: { game: "kreuz", hand: false, ouvert: false, announcement: "none" },
                      open_cards: [],
                  },
            playing: {
                turn_seat: 1,
                current_trick: [],
                last_trick: null,
                legal_cards: [],
                give_up: request,
                kontra: null,
            },
        },
    };
}

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
            marks: [
                [1, "unanswered"],
                [3, "unanswered"],
            ],
        },
        {
            request: ONE_NO,
            names: ["player 1"],
            marks: [
                [1, "unanswered"],
                [3, "declined"],
            ],
        },
    ] as const)("makes the asker wait for those who have not said no", ({ request, names, marks }) => {
        const view = giveUpView(tableWith(DECLARER, request));

        expect(view).toMatchObject({
            line: "waits",
            text: `${words["table.waitingFor"]} ${names.join(AND)}`,
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
            text: `${words["table.waitingFor"]} player 2`,
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
