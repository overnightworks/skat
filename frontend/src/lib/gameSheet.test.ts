import { describe, expect, it } from "vitest";
import { gameSheetView, hasEleventhRow } from "#lib/gameSheet.ts";
import { GIVEN_UP_SHEET, OLD_SHEET, RAMSCH_SHEET } from "#lib/series.fixtures.ts";
import { words } from "#lib/words.ts";

describe("gameSheetView of a declared game", () => {
    const view = gameSheetView(GIVEN_UP_SHEET);

    it("counts the declarer against the opponents, each by the name stored with the game", () => {
        expect(view.count).toMatchObject({
            kind: "declared",
            sides: { declarer: "Ben", opponents: expect.stringMatching(/Anna.*Cleo/u) as unknown },
            points: { declarer: 21, opponents: 99 },
        });
    });

    it("names the declarer's seat by its number", () => {
        expect(view.count).toMatchObject({ kind: "declared", declarer: { seat: 2, name: "Ben" } });
    });

    it("draws the tricks in the order sent, the declarer's apart from the opponents' and an interrupted one with no taker", () => {
        expect(
            view.cards?.tricks.map((trick) => [trick.number, trick.taker?.name ?? null, trick.points, trick.side]),
        ).toEqual([
            [1, "Ben", "11", "declarer"],
            [2, "Cleo", "12", "opponents"],
            [3, null, null, "none"],
        ]);
    });

    it("keeps the seat that played each card of a trick, the lead first", () => {
        expect(view.cards?.tricks[0]?.cards.map((each) => each.by.name)).toEqual(["Ben", "Cleo", "Anna"]);
    });

    it("marks what became of each card of a hand and keeps the display order", () => {
        const hands = view.cards?.hands.map((hand) => hand.cards.map((each) => each.state));

        expect(hands).toEqual([["unplayed", "played"], ["put-away", "played"], ["played"]]);
    });

    it("names who put which cards away", () => {
        expect(view.cards?.putAway.map((put) => [put.by.name, put.cards.length])).toEqual([["Ben", 1]]);
    });

    it("ends the game with the word of its ending and the seat that ended it", () => {
        expect(view.end).toEqual({ label: words["result.givenUp"], by: { seat: 2, name: "Ben", initial: "B" } });
    });

    it.each([
        ["thrown-down", "table.sheetThrownDown"],
        ["shortened", "table.sheetShortened"],
        ["played-open", "table.sheetPlayedOpen"],
    ] as const)("words an ending %s as %s", (ending, key) => {
        const sheet = { ...GIVEN_UP_SHEET, count: { ...GIVEN_UP_SHEET.count, ending } };

        expect(gameSheetView(sheet as typeof GIVEN_UP_SHEET).end?.label).toBe(words[key]);
    });

    it("reads a game played out with fewer than ten tricks as decided, with nobody who ended it", () => {
        const sheet = {
            ...GIVEN_UP_SHEET,
            count: { ...GIVEN_UP_SHEET.count, ending: "played-out", ended_by_seat: null },
        };

        expect(gameSheetView(sheet as typeof GIVEN_UP_SHEET).end).toEqual({
            label: words["table.sheetDecided"],
            by: null,
        });
    });

    it("gives a game played out with all ten tricks no end line", () => {
        const tricks = Array.from({ length: 10 }, (_, index) => ({
            ...(GIVEN_UP_SHEET.cards?.tricks[0] as NonNullable<typeof GIVEN_UP_SHEET.cards>["tricks"][number]),
            number: index + 1,
        }));
        const sheet = {
            ...GIVEN_UP_SHEET,
            count: { ...GIVEN_UP_SHEET.count, ending: "played-out", ended_by_seat: null },
            cards: { ...(GIVEN_UP_SHEET.cards as NonNullable<typeof GIVEN_UP_SHEET.cards>), tricks },
        };

        expect(gameSheetView(sheet as typeof GIVEN_UP_SHEET).end).toBeNull();
    });

    it("says nothing of an ending for a game with no stored cards", () => {
        expect(gameSheetView(OLD_SHEET)).toMatchObject({ cards: null, end: null });
    });
});

describe("gameSheetView of a Ramsch", () => {
    const view = gameSheetView(RAMSCH_SHEET);

    it("counts each seat's points and highlights the most, naming a seat stored without a name as nobody", () => {
        expect(
            view.count.kind === "ramsch" && view.count.seats.map((each) => [each.seat.name, each.points, each.most]),
        ).toEqual([
            ["Anna", 12, false],
            [words["table.seriesNameless"], 20, false],
            ["Cleo", 88, true],
        ]);
    });

    it("names the seat the skat counted for and draws no side for a trick", () => {
        expect(view.cards?.skatTakers.map((seat) => seat.name)).toEqual(["Anna"]);
        expect(view.cards?.tricks[0]?.side).toBe("none");
    });

    it("draws a Ramsch with no stored cards by its count alone", () => {
        expect(gameSheetView({ ...RAMSCH_SHEET, cards: null })).toMatchObject({ cards: null, end: null });
    });

    it("has no end line without a Durchmarsch and names the seat that swept as the end", () => {
        const sweep = { ...RAMSCH_SHEET, count: { kind: "ramsch", seat_points: [120, 0, 0], durchmarsch_seat: 1 } };

        expect(view.end).toBeNull();
        expect(gameSheetView(sweep as typeof RAMSCH_SHEET).end).toMatchObject({
            label: words["table.sheetDurchmarsch"],
        });
    });
});

describe("hasEleventhRow", () => {
    const trick = RAMSCH_SHEET.cards?.tricks[0] as NonNullable<typeof RAMSCH_SHEET.cards>["tricks"][number];
    const sweep = { kind: "ramsch", seat_points: [120, 0, 0], durchmarsch_seat: 1 };
    const withTricks = (count: number, ended: boolean) =>
        gameSheetView({
            ...RAMSCH_SHEET,
            count: ended ? sweep : RAMSCH_SHEET.count,
            cards: {
                ...(RAMSCH_SHEET.cards as NonNullable<typeof RAMSCH_SHEET.cards>),
                tricks: Array.from({ length: count }, (_, index) => ({ ...trick, number: index + 1 })),
            },
        } as typeof RAMSCH_SHEET);

    it.each([
        [10, false, false],
        [3, true, false],
        [10, true, true],
        [9, true, false],
    ])("tells %i tricks and an end line (%s) to have an eleventh row (%s)", (count, ended, eleventh) => {
        expect(hasEleventhRow(withTricks(count, ended))).toBe(eleventh);
    });

    it("tells a game with no stored cards to have none", () => {
        expect(hasEleventhRow(gameSheetView(OLD_SHEET))).toBe(false);
    });
});
