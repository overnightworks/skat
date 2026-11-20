import { describe, expect, it } from "vitest";
import type { Chair, Options, Table } from "../routes/(start)/tables.ts";
import { possessive } from "#lib/openChair.ts";
import { weiterBar } from "#lib/result.ts";
import {
    gameRows,
    resultOnStage,
    returnsToLobby,
    seriesCountText,
    nextSeriesLine,
    changeableSettingsOf,
    nextSettingsOf,
    nextSettingsRevisionOf,
    seriesEndAnswerBy,
    seriesEndAsk,
    seriesEndMarks,
    seriesEndOffered,
    seriesEndOnStage,
    seriesEndView,
    seriesRefusalNotice,
    seriesOver,
    standingsView,
    stopOffered,
    takenBackLine,
} from "#lib/series.ts";
import {
    chairs,
    DECLARED_ENTRY,
    LOST_ENTRY,
    RAMSCH_ENTRY,
    seriesAt,
    tableBetweenGames,
    WATCHER,
} from "#lib/series.fixtures.ts";
import { LOST_WITH_PUSHES, table as tableWith } from "#lib/result.fixtures.ts";
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

const ANSWER_BY = "2026-11-19T12:01:00Z";

describe("seriesEndAsk", () => {
    const proposal = (...agreed: number[]) =>
        seriesAt({ end_proposal: { proposer_seat: 1, agreed_seats: [1, ...agreed], answer_by: ANSWER_BY } });

    it("stands only while a proposal does", () => {
        expect(seriesEndAsk(tableBetweenGames(2, seriesAt()))).toBeNull();
    });

    it("offers Ja and Nein to a seated member who has not answered", () => {
        const ask = seriesEndAsk(tableBetweenGames(2, proposal()));

        expect(ask?.text).toBe(words["table.wantsToEndSeries"]({ name: "player 1" }));
        expect(ask?.faces.map((face) => face.initial)).toEqual(["p"]);
        expect(ask?.waits).toBe(false);
        expect(ask?.answerBy).toBe(ANSWER_BY);
        expect(ask?.buttons.map((button) => [button.answer, button.word, button.primary])).toEqual([
            ["agree", words["table.yes"], true],
            ["refuse", words["table.no"], false],
        ]);
    });

    it("makes the proposer wait for the two who have not said yes", () => {
        const ask = seriesEndAsk(tableBetweenGames(1, proposal()));

        expect(ask?.text).toBe(words["table.waitingFor"]({ names: "player 2 und player 3" }));
        expect(ask?.waits).toBe(true);
        expect(ask?.answerBy).toBe(ANSWER_BY);
        expect(ask?.buttons).toEqual([]);
    });

    it("makes the member who said yes wait for the last one", () => {
        const ask = seriesEndAsk(tableBetweenGames(2, proposal(2)));

        expect(ask?.text).toBe(words["table.waitingFor"]({ names: "player 3" }));
        expect(ask?.buttons).toEqual([]);
    });

    it.each([
        {
            name: "both asked chairs are free",
            freeSeats: [2, 3],
            text: words["table.waitingForPlayers"],
            seatedFaces: [],
        },
        {
            name: "one asked chair is free",
            freeSeats: [3],
            text: words["table.waitingFor"]({ names: "player 2" }),
            seatedFaces: [2],
        },
    ])("makes the proposer wait for the seated asked players when $name", ({ freeSeats, text, seatedFaces }) => {
        const table = tableBetweenGames(1, proposal());
        const freed = table.chairs.map((chair) =>
            freeSeats.includes(chair.seat) ? { ...chair, occupant_name: null } : chair,
        );

        const ask = seriesEndAsk({ ...table, chairs: freed });

        expect(ask?.text).toBe(text);
        expect(ask?.faces.map((face) => face.seat)).toEqual(seatedFaces);
        expect(ask?.waits).toBe(true);
    });

    it("tells a watcher who proposed and gives no answer to tap", () => {
        const ask = seriesEndAsk(tableBetweenGames(WATCHER, proposal()));

        expect(ask?.text).toBe(words["table.wantsToEndSeries"]({ name: "player 1" }));
        expect(ask?.buttons).toEqual([]);
    });
});

describe("what a proposal puts at the chairs", () => {
    const proposed = seriesAt({
        end_proposal: { proposer_seat: 1, agreed_seats: [1, 2], answer_by: ANSWER_BY },
    });
    const refused = seriesAt({ end_refused_seats: [2, 3] });

    it("marks the seats that said yes and those still to answer", () => {
        expect([...seriesEndMarks(tableBetweenGames(3, proposed))]).toEqual([
            [1, "agreed"],
            [2, "agreed"],
            [3, "unanswered"],
        ]);
    });

    it("marks the seats that refused, or stayed silent, until the next hand", () => {
        expect([...seriesEndMarks(tableBetweenGames(1, refused))]).toEqual([
            [2, "declined"],
            [3, "declined"],
        ]);
        expect(seriesEndMarks(tableBetweenGames(1, seriesAt())).size).toBe(0);
    });

    it("marks no seat of a table without a series", () => {
        expect(seriesEndMarks(tableBetweenGames(1, null)).size).toBe(0);
    });

    it("names the seats that refused, one or several, and none while a proposal stands", () => {
        expect(seriesRefusalNotice(tableBetweenGames(1, seriesAt({ end_refused_seats: [2] })))?.text).toBe(
            words["table.refusedToEndOne"]({ names: "player 2" }),
        );
        expect(seriesRefusalNotice(tableBetweenGames(1, refused))?.text).toBe(
            words["table.refusedToEndMany"]({ names: "player 2 und player 3" }),
        );
        expect(seriesRefusalNotice(tableBetweenGames(1, proposed))).toBeNull();
        expect(seriesRefusalNotice(tableBetweenGames(1, seriesAt()))).toBeNull();
    });

    it("names nobody when the seats that refused have no one seated", () => {
        const table = tableBetweenGames(1, refused);
        const vacated = table.chairs.map((chair) => ({
            ...chair,
            occupant_name: chair.seat === 1 ? chair.occupant_name : null,
        }));

        expect(seriesRefusalNotice({ ...table, chairs: vacated })).toBeNull();
    });

    it.each([
        { name: "a standing proposal", series: proposed, expected: true },
        { name: "a refusal", series: refused, expected: true },
        { name: "neither", series: seriesAt(), expected: false },
        { name: "no series", series: null, expected: false },
    ])("takes the stage of the last result for $name: $expected", ({ series, expected }) => {
        expect(seriesEndOnStage(tableBetweenGames(1, series))).toBe(expected);
    });
});

describe("seriesEndView", () => {
    it("gathers the ask and the marks of a standing proposal, and no refusal line", () => {
        const view = seriesEndView(
            tableBetweenGames(
                2,
                seriesAt({ end_proposal: { proposer_seat: 1, agreed_seats: [1], answer_by: ANSWER_BY } }),
            ),
        );

        expect(view.ask).not.toBeNull();
        expect(view.marks.get(1)).toBe("agreed");
        expect(view.onStage).toBe(true);
        expect(view.refusal).toBeNull();
    });

    it("gathers the refusal line and the crosses of a refused proposal, and no ask", () => {
        const view = seriesEndView(tableBetweenGames(1, seriesAt({ end_refused_seats: [2] })));

        expect(view.ask).toBeNull();
        expect(view.marks.get(2)).toBe("declined");
        expect(view.onStage).toBe(true);
        expect(view.refusal).not.toBeNull();
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
            series: seriesAt({ end_proposal: { proposer_seat: 2, agreed_seats: [2], answer_by: ANSWER_BY } }),
            expected: false,
        },
        { name: "a series that is over", mine: 1, series: seriesAt({ over: true }), expected: false },
        {
            name: "a proposal refused since the last hand",
            mine: 1,
            series: seriesAt({ end_refused_seats: [2] }),
            expected: false,
        },
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
        { display_name: "player 1", seat: 1, kind: "person" as const, total: 502, won: 10, lost: 4, place: 1 },
        { display_name: "player 2", seat: 1, kind: "person" as const, total: -365, won: 7, lost: 3, place: 2 },
        { display_name: "player 3", seat: 1, kind: "person" as const, total: -365, won: 7, lost: 3, place: 2 },
        { display_name: "player 4", seat: 1, kind: "person" as const, total: 118, won: 4, lost: 1, place: 4 },
        { display_name: null, seat: 1, kind: "person" as const, total: 5, won: 0, lost: 0, place: 5 },
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

    it("gives each account the seat it last held and whether an agent held it", () => {
        const view = standingsView(
            ended({
                standings: [
                    { ...standings[0], seat: 3, kind: "agent" },
                    { ...standings[1], seat: 2, kind: null },
                ],
            }),
        );

        expect(view?.rows.map((row) => [row.seat, row.agent])).toEqual([
            [3, true],
            [2, false],
        ]);
    });

    it("marks who has left the series and the seats of the winner", () => {
        const view = standingsView(ended());

        expect(view?.rows.map((row) => row.gone)).toEqual([false, false, false, true, true]);
        expect(view?.rows.map((row) => row.winner)).toEqual([true, false, false, false, false]);
        expect([...(view?.winnerSeats ?? [])]).toEqual([1]);
    });

    it("marks no chair for a winner who has left, and ignores a free chair", () => {
        const table = ended({ standings: [{ ...standings[3], display_name: "player 9", place: 1 }] });
        table.chairs[2] = { ...table.chairs[2], occupant_name: null } as Chair;

        const view = standingsView(table);

        expect(view?.rows.map((row) => row.gone)).toEqual([true]);
        expect(view?.winnerSeats.size).toBe(0);
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

describe("resultOnStage", () => {
    const ended = tableBetweenGames(2, seriesAt({ over: true, standings: [], game_number: 36 }));

    it("is true while a declared game's result stands", () => {
        expect(resultOnStage(tableWith(1, {}))).toBe(true);
    });

    it("is true while a Ramsch's reckoning stands", () => {
        expect(resultOnStage({ ...tableWith(1, null), result: LOST_WITH_PUSHES })).toBe(true);
    });

    it("is true while the standings stand", () => {
        expect(resultOnStage(ended)).toBe(true);
    });

    it("is false between games with no result", () => {
        expect(resultOnStage(tableBetweenGames(1, seriesAt()))).toBe(false);
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

describe("the series' end", () => {
    const over = (mine: number, changes: Parameters<typeof seriesAt>[0] = {}) =>
        tableBetweenGames(mine, seriesAt({ over: true, standings: [], ...changes }));
    const NO_RULES: Options = {
        show_running_points: false,
        kontra: null,
        bock: null,
        ramsch: null,
        give_up: { partner_agrees: false, any_time: false },
    };

    it.each([
        { name: "a seated member of a series that is over", table: over(1), expected: true },
        { name: "a watcher of a series that is over", table: over(WATCHER), expected: false },
        { name: "a seated member of a series that runs", table: tableBetweenGames(1, seriesAt()), expected: false },
        { name: "a seated member of a table with no series", table: tableBetweenGames(1, null), expected: false },
    ])("offers „Aufhören“ to $name: $expected", ({ table, expected }) => {
        expect(stopOffered(table)).toBe(expected);
    });

    it("names the length and the rules the next series begins with", () => {
        const table = { ...over(1), options: NO_RULES };

        expect(nextSeriesLine(table)).toEqual({
            length: words["table.seriesGames"](36),
            chips: [{ id: "official", word: words["rules.chipOfficial"], count: null }],
        });
    });

    const WITH_KONTRA: Options = {
        ...NO_RULES,
        kontra: { sayer: "bidders-only", reach: "up-to-hirsch", deadline: "own-card" },
    };

    it("names the settings a seat saved for the next series over the last series' own", () => {
        const table = {
            ...over(1, { next_settings: { game_count: 12, options: WITH_KONTRA, revision: 2 } }),
            options: NO_RULES,
        };

        expect(nextSeriesLine(table)).toEqual({
            length: words["table.seriesGames"](12),
            chips: [{ id: "kontra", word: words["rules.chipKontra"], count: null }],
        });
    });

    it("starts the sheet and names the revision from the saved settings, else from the last series as revision 0", () => {
        const saved = { game_count: 12, options: WITH_KONTRA, revision: 2 };

        expect(nextSettingsOf({ ...over(1, { next_settings: saved }), options: NO_RULES })).toEqual(saved);
        expect(nextSettingsOf({ ...over(1), options: NO_RULES })).toEqual({
            game_count: 36,
            options: NO_RULES,
            revision: 0,
        });
        expect(nextSettingsOf(tableBetweenGames(1, seriesAt()))).toBeNull();
    });

    it("names the saved revision, else revision 0 when the table has no settings to name", () => {
        const saved = { game_count: 12, options: WITH_KONTRA, revision: 2 };

        expect([
            nextSettingsRevisionOf({ ...over(1, { next_settings: saved }), options: NO_RULES }),
            nextSettingsRevisionOf({ ...over(1), options: NO_RULES }),
            nextSettingsRevisionOf(over(1)),
        ]).toEqual([2, 0, 0]);
    });

    it.each([
        { name: "a seated member of a series that is over", table: { ...over(1), options: NO_RULES }, expected: true },
        { name: "a watcher of a series that is over", table: { ...over(WATCHER), options: NO_RULES }, expected: false },
        {
            name: "a seated member of a series that runs",
            table: { ...tableBetweenGames(1, seriesAt()), options: NO_RULES },
            expected: false,
        },
        { name: "a seated member of a table that has no options", table: over(1), expected: false },
    ])("lets $name change the next settings: $expected", ({ table, expected }) => {
        expect(changeableSettingsOf(table) !== null).toBe(expected);
    });

    it("names whose „Neue Serie“ a save takes back: the other seats that chose it", () => {
        const table = tableBetweenGames(1, seriesAt({ over: true, standings: [] }), [1, 2]);

        expect(takenBackLine(table)).toBe(words["table.nextSeriesTakeBack"]({ names: possessive("player 2") }));
    });

    it("names no one when no other seat has chosen „Neue Serie“", () => {
        expect(takenBackLine(tableBetweenGames(1, seriesAt({ over: true, standings: [] }), [1]))).toBeNull();
    });

    it.each([
        { name: "a series that runs", table: { ...tableBetweenGames(1, seriesAt()), options: NO_RULES } },
        { name: "a table that has no options", table: over(1) },
    ])("draws no line of next settings for $name", ({ table }) => {
        expect(nextSeriesLine(table)).toBeNull();
    });

    it("gives the instant the silent seats end the table once the first chose „Neue Serie“", () => {
        expect(seriesEndAnswerBy(over(1, { new_series_answer_by: ANSWER_BY }))).toBe(ANSWER_BY);
    });

    it.each([
        { name: "no seat chose yet", table: over(1) },
        { name: "the series runs", table: tableBetweenGames(1, seriesAt({ new_series_answer_by: ANSWER_BY })) },
        { name: "there is no series", table: tableBetweenGames(1, null) },
    ])("gives no minute while $name", ({ table }) => {
        expect(seriesEndAnswerBy(table)).toBeNull();
    });

    const PLAYED = { standings: null, game_count: null };
    const stopped: Table = {
        ...over(1),
        ended: { ...PLAYED, reason: "closed", empty_seconds: null, unplayed_days: null, closed_by_name: null },
    };
    const named: Table = {
        ...over(1),
        ended: { ...PLAYED, reason: "closed", empty_seconds: null, unplayed_days: null, closed_by_name: "Anna" },
    };
    const emptied: Table = {
        ...over(1),
        ended: { ...PLAYED, reason: "empty", empty_seconds: 60, unplayed_days: null, closed_by_name: null },
    };

    it.each([
        {
            name: "a page that showed the live table „Aufhören“ ended",
            previous: over(1),
            table: stopped,
            expected: true,
        },
        {
            name: "a page that opened the link of a stopped table",
            previous: undefined,
            table: stopped,
            expected: false,
        },
        { name: "a page that already showed the stopped table", previous: stopped, table: stopped, expected: false },
        { name: "a page whose live table ended another way", previous: over(1), table: emptied, expected: false },
        { name: "a page whose live table an opener closed by name", previous: over(1), table: named, expected: false },
    ])("returns to the lobby from $name: $expected", ({ previous, table, expected }) => {
        expect(returnsToLobby(previous, table)).toBe(expected);
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
            subjectSeat: 2,
            agent: false,
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
            subjectSeat: 2,
            agent: true,
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
                { name: "player 3", kind: "person" as const, score: 120 },
                { name: "player 1", kind: "person" as const, score: 0 },
                { name: "player 2", kind: "person" as const, score: 0 },
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

    it("names a Ramsch's subject by seat, though two seats carry the same name", () => {
        const twins = {
            ...RAMSCH_ENTRY,
            seats: [
                { name: null, kind: null, score: 0 },
                { name: null, kind: null, score: 0 },
                { name: null, kind: null, score: -40 },
            ],
        };
        const [row] = gameRows([twins]);

        expect(row).toMatchObject({ subjectSeat: 3 });
    });

    it("names a declarer stored without a name as nobody in particular", () => {
        const [row] = gameRows([{ ...DECLARED_ENTRY, declarer_name: null }]);

        expect(row).toMatchObject({
            name: words["table.seriesNameless"],
            initial: words["table.seriesNameless"].slice(0, 1),
        });
    });
});
