import { faceOf, type AnswerMark, type AskButton, type AskView } from "#lib/giveUp.ts";
import { listFormat, words } from "#lib/words.ts";
import type { AbortAnswer, Table } from "../routes/(start)/tables.ts";

// What the table says about the vote to abort the running hand while a chair of it is open, read from the hand's own
// fields: the page decides no rule.
export type AbortView = {
    // The strip offers the first yes: a seated viewer, a vote possible and none standing.
    offered: boolean;
    // The plaque of a standing vote: what it says and what the viewer may answer; null while none stands.
    ask: AskView<AbortAnswer> | null;
    // The chairs a proposer waits for.
    marks: ReadonlyMap<number, AnswerMark>;
};

const ABORT_BUTTONS: AskButton<AbortAnswer>[] = [
    { answer: "agree", word: words["table.abort"], icon: "check", primary: true },
    { answer: "refuse", word: words["table.abortWait"], icon: "cross", primary: false },
];

const NO_VOTE: AbortView = { offered: false, ask: null, marks: new Map() };

export function abortView(table: Table): AbortView {
    const hand = table.hand;
    if (hand === null) return NO_VOTE;
    const viewerSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    if (hand.abort === null) return { ...NO_VOTE, offered: hand.abortable && viewerSeat !== undefined };
    const proposerSeats = hand.abort;
    const proposing = viewerSeat !== undefined && proposerSeats.includes(viewerSeat);
    const unansweredSeats = table.chairs
        .filter((chair) => chair.occupant_name !== null && !proposerSeats.includes(chair.seat))
        .map((chair) => chair.seat);
    const faces = (proposing ? unansweredSeats : proposerSeats).map((seat) => faceOf(table.chairs, seat));
    const names = listFormat.format(faces.map((face) => face.name));
    return {
        offered: false,
        ask: {
            text: proposing ? words["table.waitingFor"]({ names }) : words["table.wantsToAbort"]({ name: names }),
            faces,
            waits: proposing,
            buttons: viewerSeat === undefined || proposing ? [] : ABORT_BUTTONS,
        },
        marks: new Map(proposing ? unansweredSeats.map((seat) => [seat, "unanswered"]) : []),
    };
}
