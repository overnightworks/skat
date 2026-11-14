import { declinableWord, keyWord } from "#lib/kontra.ts";
import { handWaits, type SeatNotice } from "#lib/openChair.ts";
import { gameInPlay } from "#lib/playView.ts";
import { listFormat, words } from "#lib/words.ts";
import type { Chair, GiveUpAnswer, Table } from "../routes/(start)/tables.ts";

// What a chair carries about a question to the table: it said no, has not answered yet, or has tapped „Weiter“ or not.
export type AnswerMark = "declined" | "unanswered" | "ready" | "unready";
export type AskFace = { seat: number; name: string; initial: string };
export type AskButton<Answer extends string> = {
    answer: Answer;
    word: string;
    icon: "check" | "play" | "cross";
    // The answer that moves the table on is drawn as the stage's button, the other as glass.
    primary: boolean;
};
// What a plaque that asks the table says: the faces it names, the line, and the answers the viewer may give.
export type AskView<Answer extends string> = {
    text: string;
    faces: AskFace[];
    waits: boolean;
    buttons: AskButton<Answer>[];
};

export type GiveUpLine = "wants-to-give-up" | "gives-up" | "waits";

// What the plaque says about a standing request and what the viewer may answer, read from the request's own fields.
export type GiveUpView = {
    line: GiveUpLine;
    text: string;
    // The asker's face, or the faces of those the asker waits for.
    faces: AskFace[];
    answers: GiveUpAnswer[];
    marks: ReadonlyMap<number, AnswerMark>;
    // The declarer's side may not play a card while an opponent's request stands.
    cardsHeld: boolean;
};

// The key „Aufgeben“ on the bar of every seated person while a declared game is played, a Grand Hand declared in a
// Ramsch's stage included; it goes round on a phone while the strip carries „Kontra“ beside it, but keeps its word
// when the pair „Kontra“ and „Kein Kontra“ stands in a bar of its own above.
export function giveUpKey(table: Table): { round: boolean } | null {
    const seated = table.chairs.some((chair) => chair.is_mine);
    if (!seated || gameInPlay(table) === null || handWaits(table.hand)) return null;
    return { round: keyWord(table) !== null && declinableWord(table) === null };
}

export function faceOf(chairs: readonly Chair[], seat: number): AskFace {
    // A chair of a running hand is occupied.
    const name = (chairs.find((chair) => chair.seat === seat) as Chair).occupant_name as string;
    return { seat, name, initial: name.slice(0, 1) };
}

// The answerers are the side that did not ask; while a chair is open the request is not the plaque's to show.
export function giveUpView(table: Table): GiveUpView | null {
    const inPlay = gameInPlay(table);
    const request = inPlay?.playing.give_up;
    if (inPlay === null || !request || handWaits(table.hand)) return null;
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
    const marks = new Map<number, AnswerMark>(unansweredSeats.map((seat) => [seat, "unanswered"]));
    if (declinedSeat !== null) marks.set(declinedSeat, "declined");

    const faces = (asking ? pendingSeats : [askerSeat]).map((seat) => faceOf(table.chairs, seat));
    const names = listFormat.format(faces.map((face) => face.name));
    const askedLine = declarerAsks ? "wants-to-give-up" : "gives-up";
    const askedSentence = declarerAsks ? words["table.wantsToGiveUp"] : words["table.givesUp"];
    const offeredAnswers: GiveUpAnswer[] = viewerSeat === declinedSeat ? ["agree"] : ["agree", "decline"];
    return {
        line: asking ? "waits" : askedLine,
        // Not asking, `faces` holds the one asker, so the asked sentence names exactly one asker.
        text: asking ? words["table.waitingFor"]({ names }) : askedSentence({ name: names }),
        faces,
        answers: answering ? offeredAnswers : [],
        marks,
        cardsHeld: !declarerAsks,
    };
}

// The notice after the second no: the refusing seats play on, named in the page's list format.
export function refusalNotice(chairs: readonly Chair[], seats: readonly number[]): SeatNotice {
    const faces = seats.map((seat) => faceOf(chairs, seat));
    return {
        text: words["table.playingOn"]({ names: listFormat.format(faces.map((face) => face.name)) }),
        initials: faces.map((face) => face.initial),
        seat: null,
        occupied: false,
    };
}

const GIVE_UP_BUTTONS: Record<GiveUpAnswer, AskButton<GiveUpAnswer>> = {
    agree: { answer: "agree", word: words["table.accept"], icon: "check", primary: true },
    decline: { answer: "decline", word: words["table.playOn"], icon: "play", primary: false },
};

// The plaque's drawing of the request: what it says and the answers the viewer may give.
export function giveUpAsk(view: GiveUpView): AskView<GiveUpAnswer> {
    return {
        text: view.text,
        faces: view.faces,
        waits: view.line === "waits",
        buttons: view.answers.map((answer) => GIVE_UP_BUTTONS[answer]),
    };
}
