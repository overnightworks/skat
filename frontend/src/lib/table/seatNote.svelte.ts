import { noticeStanding, type SeatNotice } from "#lib/openChair.ts";
import type { Table } from "../../routes/(start)/tables.ts";

const SEAT_NOTE_MILLISECONDS = 4000;

let standing: SeatNotice | null = $state(null);
let timer: ReturnType<typeof setTimeout> | undefined;

/** The sentence that names who has just left or taken a chair of the table, while it stands. */
export function seatNote(): SeatNotice | null {
    return standing;
}

/**
 * Takes in what a streamed table brought: its sentence, if it brought one, stands for a moment in place of the last,
 * and a sentence about a chair goes as soon as that chair changes hands again.
 */
export function tellSeats(brought: SeatNotice | null, table: Table): void {
    if (brought !== null) {
        standing = brought;
        clearTimeout(timer);
        timer = setTimeout(() => (standing = null), SEAT_NOTE_MILLISECONDS);
    }
    standing = noticeStanding(standing, table);
}

/** No sentence stands, as on a table the page has just opened or left. */
export function resetSeatNote(): void {
    standing = null;
    clearTimeout(timer);
}
