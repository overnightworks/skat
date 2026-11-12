import { gameInPlay } from "#lib/playView.ts";
import { words } from "#lib/words.ts";
import type { Chair, GiveUpAnswer, Table } from "../routes/(start)/tables.ts";

export type GiveUpLine = "wants-to-give-up" | "gives-up" | "waits";
export type GiveUpMark = "declined" | "unanswered";
export type GiveUpFace = { seat: number; name: string; initial: string };

// What the plaque says about a standing request and what the viewer may answer, read from the request's own fields.
export type GiveUpView = {
    line: GiveUpLine;
    text: string;
    // The asker's face, or the faces of those the asker waits for.
    faces: GiveUpFace[];
    answers: GiveUpAnswer[];
    marks: ReadonlyMap<number, GiveUpMark>;
    // The declarer's side may not play a card while an opponent's request stands.
    cardsHeld: boolean;
};

function faceOf(chairs: readonly Chair[], seat: number): GiveUpFace {
    // A chair of a running hand is occupied.
    const name = (chairs.find((chair) => chair.seat === seat) as Chair).occupant_name as string;
    return { seat, name, initial: name.slice(0, 1) };
}

// The answerers are the side that did not ask; while a chair is open the request is not the plaque's to show.
export function giveUpView(table: Table): GiveUpView | null {
    const inPlay = gameInPlay(table);
    const request = inPlay?.playing.give_up;
    if (inPlay === null || !request || table.hand?.waiting_seat !== null) return null;
    const { declarerSeat } = inPlay;
    const { asking_seat: askerSeat, declined_seat: declinedSeat } = request;
    const viewerSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    const declarerAsks = askerSeat === declarerSeat;
    const answererSeats = declarerAsks
        ? table.chairs.map((chair) => chair.seat).filter((seat) => seat !== declarerSeat)
        : [declarerSeat];
    const pendingSeats = answererSeats.filter((seat) => seat !== declinedSeat);
    const asking = viewerSeat === askerSeat;
    const answering = viewerSeat !== undefined && answererSeats.includes(viewerSeat);
    const unansweredSeats = asking ? pendingSeats : [];
    const marks = new Map<number, GiveUpMark>(unansweredSeats.map((seat) => [seat, "unanswered"]));
    if (declinedSeat !== null) marks.set(declinedSeat, "declined");

    const faces = (asking ? pendingSeats : [askerSeat]).map((seat) => faceOf(table.chairs, seat));
    const names = faces.map((face) => face.name).join(` ${words["result.and"]} `);
    const askedLine = declarerAsks ? "wants-to-give-up" : "gives-up";
    const askedWord = declarerAsks ? words["table.wantsToGiveUp"] : words["table.givesUp"];
    return {
        line: asking ? "waits" : askedLine,
        text: asking ? `${words["table.waitingFor"]} ${names}` : `${names} ${askedWord}`,
        faces,
        answers: answering ? (viewerSeat === declinedSeat ? ["agree"] : ["agree", "decline"]) : [],
        marks,
        cardsHeld: !declarerAsks,
    };
}
