import type { Cue } from "#lib/cues.ts";
import { handWaits, type SeatNotice } from "#lib/openChair.ts";
import { gameInPlay } from "#lib/playView.ts";
import { LEVEL_WORDS } from "#lib/result.ts";
import { listFormat, words } from "#lib/words.ts";
import type { MarkedPart } from "overnightworks-design";
import {
    TABLE_GIVE_UP_AGREE_SUFFIX,
    TABLE_GIVE_UP_DECLINE_SUFFIX,
    TABLE_GIVE_UP_SUFFIX,
    TABLE_PLAY_OPEN_SUFFIX,
    TABLE_SHORTEN_SUFFIX,
} from "#lib/wire.ts";
import {
    post,
    type Chair,
    type GiveUp,
    type Outcome,
    type Playing,
    type Shortening,
    type Table,
} from "../routes/(start)/tables.ts";

export type GiveUpAnswer = "agree" | "decline";

// What a chair carries about a question to the table: it said no or yes, has not answered yet, has tapped „Weiter“ or
// not, or plays open with its cards on the felt.
export type AnswerMark = "declined" | "agreed" | "unanswered" | "ready" | "unready" | "open";
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
    // The level a shortening demands, under the line; null when none is demanded.
    demand?: readonly MarkedPart<"level">[] | null;
    // A second line of the plaque, who the viewer waits for after the line that says what the viewer did.
    waitsFor?: { text: string; faces: AskFace[] } | null;
    buttons: AskButton<Answer>[];
};

export type GiveUpLine = "wants-to-give-up" | "gives-up" | "wants-to-shorten" | "plays-open" | "waits";

// What the plaque says about a standing request and what the viewer may answer, read from the request's own fields.
export type GiveUpView = {
    line: GiveUpLine;
    text: string;
    // The asker's face, or the faces of those the asker waits for.
    faces: AskFace[];
    answers: GiveUpAnswer[];
    marks: ReadonlyMap<number, AnswerMark>;
    // The level the declarer demands with his shortening; null for every other request.
    demand: string | null;
    // After an open play the one who played it also reads whom the table waits for.
    waitsFor: { text: string; faces: AskFace[] } | null;
    // The declarer's side may not play a card while an opponent's request stands.
    cardsHeld: boolean;
};

// The menu row a seated person has beside „Aufgeben“: the declarer's „Abkürzen“ and an opponent's „Offen spielen“,
// each while a declared game is played, no chair is open and no request stands.
export function shortenKey(table: Table): boolean {
    return requestKeyHolder(table) === "declarer";
}

export function playOpenKey(table: Table): boolean {
    return requestKeyHolder(table) === "opponent";
}

function requestKeyHolder(table: Table): "declarer" | "opponent" | null {
    const inPlay = gameInPlay(table);
    const viewerSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    if (inPlay === null || viewerSeat === undefined || handWaits(table.hand) || requestStands(inPlay.playing))
        return null;
    return viewerSeat === inPlay.declarerSeat ? "declarer" : "opponent";
}

function requestStands(playing: Playing): boolean {
    return playing.give_up !== null || playing.shortening !== null || playing.open_play_seat !== null;
}

// The row „Aufgeben“ in the menu of every seated person while a declared game is played, a Grand Hand declared in a
// Ramsch's stage included.
export function giveUpOffered(table: Table): boolean {
    const seated = table.chairs.some((chair) => chair.is_mine);
    return seated && gameInPlay(table) !== null && !handWaits(table.hand);
}

export function faceOf(chairs: readonly Chair[], seat: number): AskFace {
    // A chair of a running hand is occupied.
    const name = (chairs.find((chair) => chair.seat === seat) as Chair).occupant_name as string;
    return { seat, name, initial: name.slice(0, 1) };
}

// Who is asked and who asks, read from the request's own fields.
type Asked = {
    askerSeat: number;
    answererSeats: number[];
    viewerSeat: number | undefined;
    chairs: readonly Chair[];
};

function whoIsAsked(table: Table, askerSeat: number, answererSeats: number[]): Asked {
    return {
        askerSeat,
        answererSeats,
        viewerSeat: table.chairs.find((chair) => chair.is_mine)?.seat,
        chairs: table.chairs,
    };
}

const NO_DEMAND = { demand: null, waitsFor: null } as const;

// The opponents answer the declarer's request, the partner an opponent's give-up and the declarer an opponent's wrong
// open play; while a chair is open the request is not the plaque's to show.
export function giveUpView(table: Table): GiveUpView | null {
    const inPlay = gameInPlay(table);
    if (inPlay === null || handWaits(table.hand)) return null;
    const { playing, declarerSeat } = inPlay;
    const seats = table.chairs.map((chair) => chair.seat);
    const othersThan = (...asking: number[]) => seats.filter((seat) => !asking.includes(seat));
    if (playing.give_up) {
        const askerSeat = playing.give_up.asking_seat;
        const answererSeats =
            askerSeat === declarerSeat ? othersThan(declarerSeat) : othersThan(askerSeat, declarerSeat);
        return giveUpRequestView(whoIsAsked(table, askerSeat, answererSeats), playing.give_up, declarerSeat);
    }
    if (playing.shortening)
        return shorteningView(
            whoIsAsked(table, playing.shortening.asking_seat, othersThan(declarerSeat)),
            playing.shortening,
        );
    if (playing.open_play_seat !== null) return openPlayView(whoIsAsked(table, playing.open_play_seat, [declarerSeat]));
    return null;
}

function giveUpRequestView(asked: Asked, request: GiveUp, declarerSeat: number): GiveUpView {
    const { askerSeat, answererSeats, viewerSeat, chairs } = asked;
    const { declined_seat: declinedSeat } = request;
    const declarerAsks = askerSeat === declarerSeat;
    const pendingSeats = answererSeats.filter((seat) => seat !== declinedSeat);
    const asking = viewerSeat === askerSeat;
    const answering = viewerSeat !== undefined && answererSeats.includes(viewerSeat);
    const unansweredSeats = asking ? pendingSeats : [];
    const marks = new Map<number, AnswerMark>(unansweredSeats.map((seat) => [seat, "unanswered"]));
    if (declinedSeat !== null) marks.set(declinedSeat, "declined");

    const faces = (asking ? pendingSeats : [askerSeat]).map((seat) => faceOf(chairs, seat));
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
        ...NO_DEMAND,
        cardsHeld: !declarerAsks,
    };
}

// The declarer's shortening: each opponent answers yes or no; the cards stay playable, a card played ends the request.
function shorteningView(asked: Asked, request: Shortening): GiveUpView {
    const { askerSeat, answererSeats, viewerSeat, chairs } = asked;
    const { agreed_seat: agreedSeat, claim } = request;
    const pendingSeats = answererSeats.filter((seat) => seat !== agreedSeat);
    const asking = viewerSeat === askerSeat;
    const answering = viewerSeat !== undefined && answererSeats.includes(viewerSeat);
    // Whoever is not asked to answer reads who still owes the answer.
    const marks = new Map<number, AnswerMark>(answering ? [] : pendingSeats.map((seat) => [seat, "unanswered"]));
    if (agreedSeat !== null) marks.set(agreedSeat, "agreed");

    const faces = (asking ? pendingSeats : [askerSeat]).map((seat) => faceOf(chairs, seat));
    const names = listFormat.format(faces.map((face) => face.name));
    const offeredAnswers: GiveUpAnswer[] = viewerSeat === agreedSeat ? ["decline"] : ["agree", "decline"];
    return {
        line: asking ? "waits" : "wants-to-shorten",
        text: asking ? words["table.waitingFor"]({ names }) : words["table.wantsToShorten"]({ name: names }),
        faces,
        answers: answering ? offeredAnswers : [],
        marks,
        demand: claim === "none" ? null : LEVEL_WORDS[claim],
        waitsFor: null,
        cardsHeld: false,
    };
}

// An opponent's wrong open play waits for the declarer, who answers as after a give-up; every card is held meanwhile.
function openPlayView(asked: Asked): GiveUpView {
    const { askerSeat, answererSeats, viewerSeat, chairs } = asked;
    const asking = viewerSeat === askerSeat;
    const answering = viewerSeat !== undefined && answererSeats.includes(viewerSeat);
    const asker = faceOf(chairs, askerSeat);
    const awaited = answererSeats.map((seat) => faceOf(chairs, seat));
    return {
        line: "plays-open",
        text: asking ? words["table.youPlayOpen"] : words["table.playsOpen"]({ name: asker.name }),
        faces: [asker],
        answers: answering ? ["agree", "decline"] : [],
        marks: new Map<number, AnswerMark>(asking ? answererSeats.map((seat) => [seat, "unanswered"]) : []),
        demand: null,
        waitsFor: asking
            ? {
                  text: words["table.waitingFor"]({ names: listFormat.format(awaited.map((face) => face.name)) }),
                  faces: awaited,
              }
            : null,
        cardsHeld: true,
    };
}

// What the others read once when an update ended a request without the table's yes: the first such cue, none when the
// update brought none.
export function requestEndedNotice(cues: readonly Cue[], chairs: readonly Chair[]): SeatNotice | null {
    for (const cue of cues) {
        if (cue.kind === "give-up-refused") return refusalNotice(chairs, cue.seats);
        if (cue.kind === "shortening-refused" || cue.kind === "open-play-on") return playOnNotice(chairs, cue);
    }
    return null;
}

// The notice after the second no: the refusing seats play on, named in the page's list format.
function refusalNotice(chairs: readonly Chair[], seats: readonly number[]): SeatNotice {
    const faces = seats.map((seat) => faceOf(chairs, seat));
    return {
        text: words["table.playingOn"]({ names: listFormat.format(faces.map((face) => face.name)) }),
        initials: faces.map((face) => face.initial),
        seat: null,
        occupied: false,
    };
}

// The notice after the one no that ends a shortening, and after the declarer plays on against a wrong open play: the
// game goes on, with the cards of the seat named lying open.
function playOnNotice(
    chairs: readonly Chair[],
    cue: { kind: "shortening-refused" | "open-play-on"; seat: number },
): SeatNotice {
    const { name, initial } = faceOf(chairs, cue.seat);
    const sentence = cue.kind === "shortening-refused" ? words["table.saidNoPlayingOn"] : words["table.playsOpenOn"];
    return { text: sentence({ name }), initials: [initial], seat: null, occupied: false };
}

const GIVE_UP_BUTTONS: Record<GiveUpAnswer, AskButton<GiveUpAnswer>> = {
    agree: { answer: "agree", word: words["table.accept"], icon: "check", primary: true },
    decline: { answer: "decline", word: words["table.playOn"], icon: "play", primary: false },
};

// A shortening is answered with yes and no, which the page draws as a tick and a cross.
const SHORTENING_BUTTONS: Record<GiveUpAnswer, AskButton<GiveUpAnswer>> = {
    agree: { answer: "agree", word: words["table.yes"], icon: "check", primary: true },
    decline: { answer: "decline", word: words["table.no"], icon: "cross", primary: false },
};

// The plaque's drawing of the request: what it says and the answers the viewer may give.
export function giveUpAsk(view: GiveUpView): AskView<GiveUpAnswer> {
    const buttons = view.line === "wants-to-shorten" ? SHORTENING_BUTTONS : GIVE_UP_BUTTONS;
    return {
        text: view.text,
        faces: view.faces,
        waits: view.line === "waits",
        demand: view.demand === null ? null : words["table.demands"]({ level: view.demand }),
        waitsFor: view.waitsFor,
        buttons: view.answers.map((answer) => buttons[answer]),
    };
}

// The mark a chair keeps beyond a standing request: the cross of the opponent who refused the declarer's shortening,
// until a new shortening stands, and the eye of an opponent whose cards lie open.
export function openCardsMark(table: Table, seat: number): AnswerMark | undefined {
    const playing = table.hand?.playing;
    if (!playing) return undefined;
    if (playing.shortening === null && playing.shortening_refused_seat === seat) return "declined";
    return playing.open_hands.some((hand) => hand.seat === seat) ? "open" : undefined;
}

// The version is the one the page shows, so a give-up on a table that has since moved on is refused; there is no retry.
export function giveUp(id: string, version: number, commandId: string): Promise<Outcome> {
    return post(id, TABLE_GIVE_UP_SUFFIX, { command_id: commandId, version });
}

// The declarer shortens without a demanded level; the opponents answer with `answerGiveUp`.
export function shorten(id: string, version: number, commandId: string): Promise<Outcome> {
    return post(id, TABLE_SHORTEN_SUFFIX, { command_id: commandId, version });
}

// An opponent plays open: the table ends the game at once, or asks the declarer when the play was wrong.
export function playOpen(id: string, version: number, commandId: string): Promise<Outcome> {
    return post(id, TABLE_PLAY_OPEN_SUFFIX, { command_id: commandId, version });
}

const GIVE_UP_ANSWER_SUFFIXES: Record<GiveUpAnswer, string> = {
    agree: TABLE_GIVE_UP_AGREE_SUFFIX,
    decline: TABLE_GIVE_UP_DECLINE_SUFFIX,
};

// The version is the one the page shows, so an answer to a request that has since gone is refused; there is no retry.
export function answerGiveUp(id: string, version: number, commandId: string, answer: GiveUpAnswer): Promise<Outcome> {
    return post(id, GIVE_UP_ANSWER_SUFFIXES[answer], { command_id: commandId, version });
}
