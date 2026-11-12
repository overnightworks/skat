import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACCOUNT_PATH, LOBBY_EVENTS_PATH } from "#lib/wire.ts";
import { cardOf, daysLeftWords, minutesLeft, titleOf, watchLobby, type LobbyChair, type LobbyTable } from "./lobby.ts";

const NOW = Date.UTC(2026, 10, 12, 12);
const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const SECOND = 1_000;

function chairOf(seat: number, overrides: Partial<LobbyChair> = {}): LobbyChair {
    return {
        seat,
        occupant_name: ["Anna", "Ben", "Felix"][seat] ?? null,
        occupant_kind: "person",
        is_mine: false,
        ready: false,
        total: null,
        is_away: false,
        is_turn: false,
        ...overrides,
    };
}

function tableOf(overrides: Partial<LobbyTable> = {}): LobbyTable {
    return {
        id: "a".repeat(32),
        title_name: "Ben",
        game_number: 9,
        game_count: 36,
        dealt: true,
        awaits_you: false,
        waits_on: null,
        result_waits: false,
        series_over: false,
        ends_at: null,
        chairs: [chairOf(0), chairOf(1), chairOf(2, { is_mine: true })],
        ...overrides,
    };
}

function ownChairOf(table: LobbyTable): LobbyChair {
    const own = table.chairs.find((chair) => chair.is_mine);
    if (own === undefined) throw new Error("the table has no own chair");
    return own;
}

describe("titleOf", () => {
    it.each([
        ["Ben", "Bens Tisch"],
        ["Max", "Max' Tisch"],
        ["Strauß", "Strauß' Tisch"],
        ["Lars", "Lars' Tisch"],
        ["Lenz", "Lenz' Tisch"],
        ["LARS", "LARS' Tisch"],
        [null, "Tisch"],
    ])("reads %s as %s", (name, title) => {
        expect(titleOf(name)).toBe(title);
    });
});

describe("daysLeftWords", () => {
    it.each([
        [12 * DAY + HOUR, "endet in 12 Tagen"],
        [DAY, "endet in 1 Tag"],
        [2 * DAY - SECOND, "endet in 1 Tag"],
        [DAY - SECOND, "endet heute"],
        [0, "endet heute"],
        [-3 * DAY, "endet heute"],
    ])("reads an end %i ms away as %s", (away, text) => {
        expect(daysLeftWords(new Date(NOW + away).toISOString(), NOW)).toBe(text);
    });
});

describe("minutesLeft", () => {
    it.each([
        [240, 0, 4],
        [240, 10 * SECOND, 4],
        [240, 60 * SECOND, 3],
        [300, 0, 5],
        [61, 0, 2],
        [60, 0, 1],
        [3, 0, 1],
        [240, 239 * SECOND, 1],
    ])("counts %i seconds after %i ms as %i whole minutes, rounded up", (seconds, held, minutes) => {
        expect(minutesLeft(seconds, held)).toBe(minutes);
    });

    it("has nothing left once the hold has run out", () => {
        expect(minutesLeft(240, 240 * SECOND)).toBeNull();
        expect(minutesLeft(240, 300 * SECOND)).toBeNull();
    });
});

describe("cardOf", () => {
    it("titles the card with the opener's name and opens the table", () => {
        const card = cardOf(tableOf({ id: "b".repeat(32) }), NOW, 0);

        expect(card.title).toBe("Bens Tisch");
        expect(card.id).toBe("b".repeat(32));
    });

    it.each([
        [{ game_number: 9, game_count: 36 }, "Spiel 9 von 36"],
        [{ game_number: null, game_count: 36 }, "36 Spiele"],
        [{ game_number: null, game_count: 1 }, "1 Spiel"],
        [{ game_number: null, game_count: null }, null],
    ])("reads the series of %o as %s", (series, progress) => {
        expect(cardOf(tableOf(series), NOW, 0).progress).toBe(progress);
    });

    it("lists the chairs in the order the stream sends them, naming the own one Du", () => {
        const card = cardOf(tableOf(), NOW, 0);

        expect(card.seats.map((seat) => seat.name)).toEqual(["Anna", "Ben", "Du"]);
    });

    it("draws a free chair as the idle plate Frei with no total", () => {
        const free = chairOf(1, { occupant_name: null, occupant_kind: null, total: null });
        const card = cardOf(tableOf({ chairs: [chairOf(0), free, chairOf(2, { is_mine: true })] }), NOW, 0);

        expect(card.seats[1]).toMatchObject({ free: true, name: "Frei", total: null });
    });

    it("draws the running totals with a true minus sign", () => {
        const chairs = [
            chairOf(0, { total: 142 }),
            chairOf(1, { total: -30 }),
            chairOf(2, { is_mine: true, total: 0 }),
        ];

        expect(cardOf(tableOf({ chairs }), NOW, 0).seats.map((seat) => seat.total)).toEqual(["142", "−30", "0"]);
    });

    it("marks the chair whose move the hand waits for and nobody else", () => {
        const chairs = [chairOf(0), chairOf(1, { is_turn: true }), chairOf(2, { is_mine: true })];

        expect(cardOf(tableOf({ chairs }), NOW, 0).seats.map((seat) => seat.turn)).toEqual([false, true, false]);
    });

    it("draws an agent's chair as an agent", () => {
        const chairs = [chairOf(0, { occupant_kind: "agent" }), chairOf(1), chairOf(2, { is_mine: true })];

        expect(cardOf(tableOf({ chairs }), NOW, 0).seats.map((seat) => seat.agent)).toEqual([true, false, false]);
    });

    describe("away marks", () => {
        it("marks every chair the stream marks away", () => {
            const chairs = [chairOf(0, { is_away: true }), chairOf(1), chairOf(2, { is_mine: true })];

            expect(cardOf(tableOf({ chairs }), NOW, 0).seats.map((seat) => seat.away)).toEqual([true, false, false]);
        });

        it("marks the own chair when its hold runs", () => {
            const table = tableOf();
            ownChairOf(table).hold_seconds_left = 240;

            expect(cardOf(table, NOW, 0).seats[2]?.away).toBe(true);
        });

        it("marks the own chair when nobody is there and the table has its end", () => {
            const table = tableOf({ ends_at: new Date(NOW + 41 * DAY).toISOString() });

            expect(cardOf(table, NOW, 0).seats[2]?.away).toBe(true);
        });

        it("leaves the own chair unmarked where somebody is there", () => {
            expect(cardOf(tableOf(), NOW, 0).seats[2]?.away).toBe(false);
        });
    });

    describe("the minutes of a hold", () => {
        function waitingTable(): LobbyTable {
            const chairs = [
                chairOf(0, { is_away: true, hold_seconds_left: 300 }),
                chairOf(1, { occupant_name: null, occupant_kind: null }),
                chairOf(2, { is_mine: true, hold_seconds_left: 240 }),
            ];
            return tableOf({ dealt: false, game_number: null, chairs });
        }

        it("says them on every away chair, the own one and the others'", () => {
            const seats = cardOf(waitingTable(), NOW, 0).seats;

            expect(seats[0]?.hold?.note).toBe("noch 5 Min");
            expect(seats[2]?.hold?.note).toBe("noch 4 Min");
            expect(seats[1]?.hold).toBeNull();
        });

        it("titles the own chair as the own place and another chair as that person's place", () => {
            const seats = cardOf(waitingTable(), NOW, 0).seats;

            expect(seats[2]?.hold?.title).toBe("Dein Platz wird in 4 Minuten frei");
            expect(seats[0]?.hold?.title).toBe("Annas Platz wird in 5 Minuten frei");
        });

        it("counts down with the time the page has held the list", () => {
            expect(cardOf(waitingTable(), NOW, 61 * SECOND).seats[2]?.hold?.note).toBe("noch 3 Min");
            expect(cardOf(waitingTable(), NOW, 239 * SECOND).seats[2]?.hold?.note).toBe("noch 1 Min");
        });

        it("says one minute in the singular", () => {
            expect(cardOf(waitingTable(), NOW, 239 * SECOND).seats[2]?.hold?.title).toBe(
                "Dein Platz wird in 1 Minute frei",
            );
        });

        it("says nothing for a hold that ran out", () => {
            expect(cardOf(waitingTable(), NOW, 240 * SECOND).seats[2]?.hold).toBeNull();
        });

        it("says nothing for a free chair", () => {
            const free = chairOf(1, { occupant_name: null, occupant_kind: null, hold_seconds_left: 240 });
            const table = tableOf({ chairs: [chairOf(0), free, chairOf(2, { is_mine: true })] });

            expect(cardOf(table, NOW, 0).seats[1]?.hold).toBeNull();
        });

        it("says nothing where the stream sends no hold", () => {
            expect(cardOf(tableOf(), NOW, 0).seats[0]?.hold).toBeNull();
        });
    });

    describe("the chips", () => {
        const own = (overrides: Partial<LobbyChair>) => [
            chairOf(0),
            chairOf(1),
            chairOf(2, { is_mine: true, ...overrides }),
        ];

        it.each([
            ["turn", "Du bist dran"],
            ["give_up", "Du bist dran"],
        ] as const)("says Du bist dran, in accent, when the stream waits on %s", (waitsOn, text) => {
            const chips = cardOf(tableOf({ awaits_you: true, waits_on: waitsOn }), NOW, 0).chips;

            expect(chips).toEqual([{ kind: "turn", text, accent: true }]);
        });

        it.each(["kontra", "end_proposal"] as const)("draws no chip for a question of %s", (waitsOn) => {
            expect(cardOf(tableOf({ awaits_you: true, waits_on: waitsOn }), NOW, 0).chips).toEqual([]);
        });

        it("draws no chip for another person's turn or a passed-in pause", () => {
            const chairs = [chairOf(0, { is_turn: true }), chairOf(1), chairOf(2, { is_mine: true })];

            expect(cardOf(tableOf({ chairs }), NOW, 0).chips).toEqual([]);
        });

        it("says Ergebnis wartet in accent while the own Weiter is not given", () => {
            const table = tableOf({ result_waits: true, waits_on: "result", awaits_you: true, chairs: own({}) });

            expect(cardOf(table, NOW, 0).chips).toEqual([{ kind: "result", text: "Ergebnis wartet", accent: true }]);
        });

        it("turns Ergebnis wartet neutral once the own Weiter is given", () => {
            const table = tableOf({ result_waits: true, chairs: own({ ready: true }) });

            expect(cardOf(table, NOW, 0).chips).toEqual([{ kind: "result", text: "Ergebnis wartet", accent: false }]);
        });

        it("says Serie vorbei, in accent until the own Neue Serie is given and neutral after", () => {
            const waiting = tableOf({ result_waits: true, series_over: true, chairs: own({}) });
            const given = tableOf({ result_waits: true, series_over: true, chairs: own({ ready: true }) });

            expect(cardOf(waiting, NOW, 0).chips).toEqual([{ kind: "seriesOver", text: "Serie vorbei", accent: true }]);
            expect(cardOf(given, NOW, 0).chips).toEqual([{ kind: "seriesOver", text: "Serie vorbei", accent: false }]);
        });

        it("says when the table ends, neutral, after what waits", () => {
            const table = tableOf({
                result_waits: true,
                chairs: own({}),
                ends_at: new Date(NOW + 12 * DAY + HOUR).toISOString(),
            });

            expect(cardOf(table, NOW, 0).chips.map((chip) => [chip.kind, chip.text, chip.accent])).toEqual([
                ["result", "Ergebnis wartet", true],
                ["ends", "endet in 12 Tagen", false],
            ]);
        });
    });
});

class FakeEventSource {
    static opened: FakeEventSource[] = [];
    onerror: (() => void) | null = null;
    readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
    close = vi.fn();
    constructor(readonly url: string) {
        FakeEventSource.opened.push(this);
    }
    addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
        this.listeners.set(type, listener);
    }
    send(type: string, data: string) {
        this.listeners.get(type)?.({ data } as MessageEvent<string>);
    }
}

describe("watchLobby", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        FakeEventSource.opened = [];
        vi.stubGlobal("EventSource", FakeEventSource);
        vi.stubGlobal("document", {
            visibilityState: "visible",
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
        });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    it("opens the lobby stream and hands over the tables of each mine event", () => {
        const onMine = vi.fn();
        watchLobby(onMine, vi.fn());
        const table = tableOf();

        FakeEventSource.opened[0]?.send("mine", JSON.stringify({ tables: [table] }));

        expect(FakeEventSource.opened[0]?.url).toBe(LOBBY_EVENTS_PATH);
        expect(onMine).toHaveBeenCalledWith([table]);
    });

    it("reports the line as there once an event arrived", () => {
        const onConnection = vi.fn();
        watchLobby(vi.fn(), onConnection);

        FakeEventSource.opened[0]?.send("mine", JSON.stringify({ tables: [] }));

        expect(onConnection).toHaveBeenLastCalledWith(true);
    });

    it("reports the line as lost and opens a new stream by itself after a failure", async () => {
        const onConnection = vi.fn();
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200 }));
        watchLobby(vi.fn(), onConnection);

        FakeEventSource.opened[0]?.onerror?.();
        await vi.advanceTimersByTimeAsync(40_000);

        expect(onConnection).toHaveBeenCalledWith(false);
        expect(FakeEventSource.opened).toHaveLength(2);
        expect(vi.mocked(fetch)).toHaveBeenCalledWith(ACCOUNT_PATH);
    });

    it("reloads the page when the session ended, to the sign-in", async () => {
        const reload = vi.fn();
        vi.stubGlobal("location", { reload });
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401 }));
        watchLobby(vi.fn(), vi.fn());

        FakeEventSource.opened[0]?.onerror?.();
        await vi.advanceTimersByTimeAsync(0);

        expect(reload).toHaveBeenCalledOnce();
        expect(FakeEventSource.opened).toHaveLength(1);
    });
});
