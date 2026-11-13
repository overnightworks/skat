import { describe, expect, it } from "vitest";
import { weiterBar } from "#lib/result.ts";
import { gameRows, seriesCountText, seriesEndAsk, seriesEndOffered, seriesOver, standingsView } from "#lib/series.ts";
import {
    chairs,
    DECLARED_ENTRY,
    LOST_ENTRY,
    RAMSCH_ENTRY,
    seriesAt,
    tableBetweenGames,
    WATCHER,
} from "#lib/series.fixtures.ts";
import { words } from "#lib/words.ts";

describe("seriesCountText", () => {
    it("counts the game the series is at", () => {
        expect(seriesCountText(tableBetweenGames(1, seriesAt()))).toBe(
            words["table.seriesCount"]({ game: "8", count: 36 }),
        );
    });

    it.each([
        { name: "no series", series: null },
        { name: "no deal yet", series: seriesAt({ game_number: 0 }) },
        { name: "a series that is over", series: seriesAt({ over: true, standings: [] }) },
    ])("shows no count for $name", ({ series }) => {
        expect(seriesCountText(tableBetweenGames(1, series))).toBeNull();
    });
});

describe("seriesOver", () => {
    it.each([
        { series: null, expected: false },
        { series: seriesAt(), expected: false },
        { series: seriesAt({ over: true }), expected: true },
    ])("reads $series as $expected", ({ series, expected }) => {
        expect(seriesOver(tableBetweenGames(1, series))).toBe(expected);
    });
});

describe("seriesEndAsk", () => {
    const proposal = (accepter: number | null) =>
        seriesAt({ end_proposal: { proposer_seat: 1, accepter_seat: accepter } });

    it("stands only while a proposal does", () => {
        expect(seriesEndAsk(tableBetweenGames(2, seriesAt()))).toBeNull();
    });

    it("offers Ja and Nein to a seated member who has not answered", () => {
        const ask = seriesEndAsk(tableBetweenGames(2, proposal(null)));

        expect(ask?.text).toBe(words["table.wantsToEndSeries"]({ name: "player 1" }));
        expect(ask?.faces.map((face) => face.initial)).toEqual(["p"]);
        expect(ask?.waits).toBe(false);
        expect(ask?.buttons.map((button) => [button.answer, button.word, button.primary])).toEqual([
            ["agree", words["table.yes"], true],
            ["refuse", words["table.no"], false],
        ]);
    });

    it("makes the proposer wait for the two who have not said yes", () => {
        const ask = seriesEndAsk(tableBetweenGames(1, proposal(null)));

        expect(ask?.text).toBe(words["table.waitingFor"]({ names: "player 2 und player 3" }));
        expect(ask?.waits).toBe(true);
        expect(ask?.buttons).toEqual([]);
    });

    it("makes the member who said yes wait for the last one", () => {
        const ask = seriesEndAsk(tableBetweenGames(2, proposal(2)));

        expect(ask?.text).toBe(words["table.waitingFor"]({ names: "player 3" }));
        expect(ask?.buttons).toEqual([]);
    });

    it("tells a watcher who proposed and gives no answer to tap", () => {
        const ask = seriesEndAsk(tableBetweenGames(WATCHER, proposal(null)));

        expect(ask?.text).toBe(words["table.wantsToEndSeries"]({ name: "player 1" }));
        expect(ask?.buttons).toEqual([]);
    });
});

describe("seriesEndOffered", () => {
    it.each([
        { name: "a seated member between games", mine: 1, series: seriesAt(), expected: true },
        { name: "a watcher", mine: WATCHER, series: seriesAt(), expected: false },
        { name: "no deal yet", mine: 1, series: seriesAt({ game_number: 0 }), expected: false },
        {
            name: "a standing proposal",
            mine: 1,
            series: seriesAt({ end_proposal: { proposer_seat: 2, accepter_seat: null } }),
            expected: false,
        },
        { name: "a series that is over", mine: 1, series: seriesAt({ over: true }), expected: false },
        { name: "a table without a series", mine: 1, series: null, expected: false },
    ])("is $expected for $name", ({ mine, series, expected }) => {
        expect(seriesEndOffered(tableBetweenGames(mine, series))).toBe(expected);
    });

    it("is false while a hand runs", () => {
        const running = { ...tableBetweenGames(1, seriesAt()), hand: {} as never };

        expect(seriesEndOffered(running)).toBe(false);
    });
});

describe("standingsView", () => {
    const standings = [
        { display_name: "player 1", total: 502, won: 10, lost: 4, place: 1 },
        { display_name: "player 2", total: -365, won: 7, lost: 3, place: 2 },
        { display_name: "player 3", total: -365, won: 7, lost: 3, place: 2 },
        { display_name: "player 4", total: 118, won: 4, lost: 1, place: 4 },
        { display_name: null, total: 5, won: 0, lost: 0, place: 5 },
    ];
    const ended = (changes = {}) =>
        tableBetweenGames(2, seriesAt({ over: true, standings, game_number: 36, ...changes }));

    it("is none while the series runs", () => {
        expect(standingsView(tableBetweenGames(1, seriesAt()))).toBeNull();
    });

    it("ranks every account with its place, total and record as declarer", () => {
        const view = standingsView(ended());

        expect(view?.sub).toBe(words["table.seriesGames"](36));
        expect(view?.rows.map((row) => [row.place, row.name, row.total, row.record])).toEqual([
            [1, "player 1", "502", words["table.seriesRecord"]({ won: "10", lost: "4" })],
            [2, "player 2", "−365", words["table.seriesRecord"]({ won: "7", lost: "3" })],
            [2, "player 3", "−365", words["table.seriesRecord"]({ won: "7", lost: "3" })],
            [4, "player 4", "118", words["table.seriesRecord"]({ won: "4", lost: "1" })],
            [5, words["table.seriesNameless"], "5", words["table.seriesRecord"]({ won: "0", lost: "0" })],
        ]);
    });

    it("marks who has left the series and the seats of the winner", () => {
        const view = standingsView(ended());

        expect(view?.rows.map((row) => row.gone)).toEqual([false, false, false, true, true]);
        expect(view?.rows.map((row) => row.winner)).toEqual([true, false, false, false, false]);
        expect([...(view?.winnerSeats ?? [])]).toEqual([1]);
    });

    it("lets a place shared at the top share the win", () => {
        const view = standingsView(
            ended({
                standings: [
                    { ...standings[0], place: 1 },
                    { ...standings[1], place: 1 },
                ],
            }),
        );

        expect([...(view?.winnerSeats ?? [])].sort()).toEqual([1, 2]);
    });
});

describe("weiterBar after the series ended", () => {
    const ended = (mine: number, ready: number[]) =>
        tableBetweenGames(mine, seriesAt({ over: true, standings: [] }), ready);

    it("offers the tap to a seated member who has not tapped, with no result standing", () => {
        expect(weiterBar(ended(1, []))).toEqual({ kind: "tap", again: false });
    });

    it("waits for those who have not tapped", () => {
        expect(weiterBar(ended(1, [1]))).toEqual({
            kind: "wait",
            text: words["table.waitingFor"]({ names: "player 2 und player 3" }),
        });
    });

    it("gives a watcher no tap", () => {
        expect(weiterBar(ended(WATCHER, []))).toBeNull();
    });

    it("gives no bar between games while the series runs", () => {
        expect(weiterBar(tableBetweenGames(1, seriesAt()))).toBeNull();
        expect(chairs(1)).toHaveLength(3);
    });
});

describe("gameRows", () => {
    it("lists the newest game on top", () => {
        expect(gameRows([DECLARED_ENTRY, LOST_ENTRY]).map((row) => row.number)).toEqual([6, 4]);
    });

    it("names the declarer, the game with its levels, its value and the gain", () => {
        const [row] = gameRows([DECLARED_ENTRY]);

        expect(row).toMatchObject({
            number: 4,
            name: "player 2",
            initial: "p",
            line: `${words["game.handName"]({ game: words["game.grand"] })}, ${words["result.levelSchneider"]}`,
            value: "48",
            gain: "+98",
            lost: false,
        });
    });

    it("shows a lost game's loss with a minus", () => {
        const [row] = gameRows([LOST_ENTRY]);

        expect(row).toMatchObject({ gain: "−86", lost: true });
    });

    it("names a Ramsch by whoever lost it and how often its skat was pushed", () => {
        const [row] = gameRows([RAMSCH_ENTRY]);

        expect(row).toMatchObject({
            number: 7,
            name: words["table.seriesRamschOf"]({ name: "player 2" }),
            line: words["table.seriesPushed"]({ count: 2 }),
            value: "",
            gain: "−40",
            lost: true,
        });
    });

    it("names the sweeper of a Durchmarsch, who gains", () => {
        const sweep = {
            ...RAMSCH_ENTRY,
            durchmarsch: true,
            pushes: 0,
            seats: [
                { name: "player 3", score: 120 },
                { name: "player 1", score: 0 },
                { name: "player 2", score: 0 },
            ],
        };
        const [row] = gameRows([sweep]);

        expect(row).toMatchObject({
            name: words["table.seriesRamschOf"]({ name: "player 3" }),
            line: null,
            gain: "+120",
            lost: false,
        });
    });

    it("names a declarer stored without a name as nobody in particular", () => {
        const [row] = gameRows([{ ...DECLARED_ENTRY, declarer_name: null }]);

        expect(row).toMatchObject({
            name: words["table.seriesNameless"],
            initial: words["table.seriesNameless"].slice(0, 1),
        });
    });
});
