import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { attentionMark, watchTable } from "./tables.ts";
import { words } from "#lib/words.ts";

class FakeEventSource {
    static last: FakeEventSource;
    close = vi.fn();
    private readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
    constructor(readonly url: string) {
        FakeEventSource.last = this;
    }
    addEventListener(name: string, listener: (event: MessageEvent<string>) => void) {
        this.listeners.set(name, listener);
    }
    send(name: string, data: string) {
        this.listeners.get(name)?.({ data } as MessageEvent<string>);
    }
}

describe("the table stream's event attention", () => {
    beforeEach(() => {
        vi.stubGlobal("EventSource", FakeEventSource);
        vi.stubGlobal("document", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("hands the number of the other tables that wait to the page and marks the connection", () => {
        const onTable = vi.fn();
        const onAttention = vi.fn();
        const onConnection = vi.fn();
        watchTable("table-id", onTable, onAttention, onConnection);

        FakeEventSource.last.send("attention", "3");

        expect(onAttention).toHaveBeenCalledExactlyOnceWith(3);
        expect(onTable).not.toHaveBeenCalled();
        expect(onConnection).toHaveBeenCalledWith(true);
    });
});

describe("the number on the Lobby button", () => {
    it.each([
        [0, ""],
        [1, "1"],
        [9, "9"],
        [10, "9+"],
        [40, "9+"],
    ])("draws %i as %j", (count, mark) => {
        expect(attentionMark(count)).toBe(mark);
    });

    it.each([
        [1, "Lobby, 1 Tisch wartet auf dich"],
        [2, "Lobby, 2 Tische warten auf dich"],
        [12, "Lobby, 12 Tische warten auf dich"],
    ])("names the button for %i waiting tables", (count, name) => {
        expect(words["table.lobbyWaiting"](count)).toBe(name);
    });
});
