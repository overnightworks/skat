import { afterEach, describe, expect, it, vi } from "vitest";
import { isFramedInCallMode } from "./callFrame.ts";
import { CALL_MODE, MODE_QUERY_NAME } from "./wire.ts";

const TABLE_ADDRESS = "https://skat.test/t/0123456789abcdef0123456789abcdef";

function stubPage(search: string, framed: boolean): void {
    const own = {};
    vi.stubGlobal("location", { href: `${TABLE_ADDRESS}${search}` });
    vi.stubGlobal("window", { self: own, top: framed ? {} : own });
}

describe("isFramedInCallMode", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it.each([
        { search: `?${MODE_QUERY_NAME}=${CALL_MODE}`, framed: true, expected: true },
        { search: `?${MODE_QUERY_NAME}=${CALL_MODE}`, framed: false, expected: false },
        { search: "", framed: true, expected: false },
        { search: "", framed: false, expected: false },
    ])("is $expected for the address $search when framed is $framed", ({ search, framed, expected }) => {
        stubPage(search, framed);

        expect(isFramedInCallMode()).toBe(expected);
    });
});
