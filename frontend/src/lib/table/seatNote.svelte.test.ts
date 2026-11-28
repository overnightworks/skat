import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { table } from "#lib/cues.fixtures.ts";
import type { SeatNotice } from "#lib/openChair.ts";
import type { Table } from "../../routes/(start)/tables.ts";
import { resetSeatNote, seatNote, tellSeats } from "./seatNote.svelte.ts";

const SEATED = table(1, [10, 10, 10]);
const OPENED: Table = {
    ...SEATED,
    chairs: SEATED.chairs.map((chair) => (chair.seat === 2 ? { ...chair, occupant_name: null } : chair)),
};
const LEFT: SeatNotice = { text: "player 2 ist aufgestanden", initials: ["p"], seat: 2, occupied: false };
const PLAYS_ON: SeatNotice = { text: "Dora spielt weiter", initials: ["D"], seat: 2, occupied: true };

beforeEach(() => {
    vi.useFakeTimers();
});

afterEach(() => {
    resetSeatNote();
    vi.useRealTimers();
});

describe("the seat note", () => {
    it("stands from the table that brought it and goes after a moment", () => {
        tellSeats(LEFT, OPENED);
        expect(seatNote()).toEqual(LEFT);

        vi.advanceTimersByTime(3999);
        expect(seatNote()).toEqual(LEFT);
        vi.advanceTimersByTime(1);
        expect(seatNote()).toBeNull();
    });

    it("stays through a table that brings no sentence while its chair stays as it was", () => {
        tellSeats(LEFT, OPENED);

        tellSeats(null, { ...OPENED, version: 2 });

        expect(seatNote()).toEqual(LEFT);
    });

    it("goes as soon as its chair changes hands again", () => {
        tellSeats(LEFT, OPENED);

        tellSeats(null, SEATED);

        expect(seatNote()).toBeNull();
    });

    it("gives way to a newer sentence, which stands its own full moment", () => {
        tellSeats(LEFT, OPENED);
        vi.advanceTimersByTime(3000);

        tellSeats(PLAYS_ON, SEATED);
        vi.advanceTimersByTime(3999);

        expect(seatNote()).toEqual(PLAYS_ON);
        vi.advanceTimersByTime(1);
        expect(seatNote()).toBeNull();
    });

    it("is gone after a reset and stays gone when its moment would have ended", () => {
        tellSeats(LEFT, OPENED);

        resetSeatNote();
        tellSeats(PLAYS_ON, SEATED);
        vi.advanceTimersByTime(3999);

        expect(seatNote()).toEqual(PLAYS_ON);
    });
});
