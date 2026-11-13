import { listFormat, words } from "#lib/words.ts";
import { sideNames, type SideNames } from "#lib/playView.ts";
import { WORD_TOKENS } from "#lib/wire.ts";
import {
    gameLabel,
    gameWord,
    isSuitGame,
    type Announcement,
    type Chair,
    type Level,
    type RamschResult,
    type RamschSeat,
    type Result,
    type Sides,
    type SeatGain,
    type Suit,
    type Table,
    type Word,
} from "../routes/(start)/tables.ts";

export type ReckoningRow = {
    seat: number;
    name: string | null;
    initial: string;
    gain: number;
    gainText: string;
    won: boolean;
};
// One counted step of the game's value; the matadors chip stands unticked before the ticked levels.
export type Chip = { word: string; ticked: boolean };
// The value's product as the server counted it: the multiplier times the base value, and the value itself only when
// the score is not that value (a lost game). Null has neither multiplier nor base.
export type Equation = { multiplier: number | null; base: number | null; product: number | null };
// What the game added to the declarer's side, step by step, and for a lost game what each opponent gets.
export type ListLine = { side: string; steps: string[]; share: string | null };
// The word stamped beside the game's name: „Aufgegeben“ carries the face of whoever gave up, „Überreizt“ has none.
export type Stamp = { word: string; face: string | null };
export type ResultView = {
    word: string;
    // The mark's shape: a tick when the word is good news for this viewer, a cross when it is not.
    good: boolean;
    // The trump suit of a suit game; Grand and Null have none.
    suit: Suit | null;
    // The word a game that is no suit stands for in the equation: Grand, or a Null game's whole name.
    gameWord: string;
    // The game's name with its levels; an opponent's line names whose game it was first.
    gameLine: string;
    // The announcement that was missed, said as the line under the result.
    missed: string | null;
    chips: Chip[];
    // The Kontra words said, each held with the factor it doubled the score to; none when nobody doubled.
    doublings: string[];
    equation: Equation | null;
    // Null unless the game was given up or overbid.
    stamp: Stamp | null;
    // The line under the stamp: what the game was worth against what was bid and the value it was raised to.
    raise: string | null;
    // Whether the score was doubled: the lost game's ×2.
    doubled: boolean;
    score: string;
    list: ListLine;
    sides: SideNames;
    // Null is not played for card points, so it has no bar.
    points: Sides | null;
    // A long reckoning packs tighter so the card still ends above the own chair.
    snug: boolean;
    rows: ReckoningRow[];
};
// The head's mark: a tick for the sweeper of a Durchmarsch, a cross for the viewer who lost; another's loss has none.
export type RamschMark = "tick" | "cross";
export type EyeCount = { seat: number; name: string; points: number; strong: boolean };
// The Ramsch's card: its head, the loser's eyes, the factors that multiply them, the value and each seat's eyes.
export type RamschView = {
    word: string;
    mark: RamschMark | null;
    // Only the viewer's own loss turns the card to the lost look.
    lost: boolean;
    // The eyes of the loser, or of the sweeper of a Durchmarsch.
    eyes: string;
    chips: string[];
    score: string;
    // The value stands in red when it is a loss.
    loss: boolean;
    // The viewer's own chair comes first; the loser's or the sweeper's count stands out.
    counts: EyeCount[];
    rows: ReckoningRow[];
};
// `again` marks a tap that asks for a deal that failed: it stays tappable however often it is tapped.
export type WeiterBar = { kind: "tap"; again: boolean } | { kind: "wait"; text: string };

const MINUS = "−";
const SNUG_LEVELS = 2;

const LEVEL_WORDS: Record<Level, string> = {
    spiel: words["result.levelSpiel"],
    hand: words["result.hand"],
    schneider: words["result.levelSchneider"],
    schneider_announced: words["result.announcedSchneider"],
    schwarz: words["result.levelSchwarz"],
    schwarz_announced: words["result.announcedSchwarz"],
    ouvert: words["result.levelOuvert"],
};

export function withMinus(number: number): string {
    return number < 0 ? `${MINUS}${String(-number)}` : String(number);
}

function signed(score: number): string {
    return score < 0 ? withMinus(score) : `+${String(score)}`;
}

function nameOf(chairs: readonly Chair[], seat: number): string | null {
    return (chairs.find((chair) => chair.seat === seat) as Chair).occupant_name;
}

// A chair that has been left while the result stands reads as free, as its coaster does.
function shownName(chairs: readonly Chair[], seat: number): string {
    return nameOf(chairs, seat) ?? words["result.seatFree"];
}

// The viewer's own chair comes first, then the others in seat order; a watcher has no own chair.
function ownFirst(chairs: readonly Chair[]): Chair[] {
    const own = chairs.filter((chair) => chair.is_mine);
    return [...own, ...chairs.filter((chair) => !chair.is_mine)];
}

// The announcement's miss as its own sentence; no announcement has none.
const MISSED_WORDS: Record<Announcement, string | null> = {
    none: null,
    schneider: words["result.missedSchneider"],
    schwarz: words["result.missedSchwarz"],
};

// A Bock game's factor is one held chip; a game outside Bock has no such step.
function bockWordOf(factor: number): string[] {
    return factor > 1 ? [words["bock.factor"]({ factor: String(factor) })] : [];
}

const WORD_TEXTS: Record<Word, string> = {
    kontra: words["result.wordKontra"],
    re: words["result.wordRe"],
    supra: words["result.wordSupra"],
    hirsch: words["result.wordHirsch"],
};

// Every word up to the last one said was said, each doubling the score once more; the Bock factor is held beside them.
function doublingsOf({ kontra, bock_factor }: Result): string[] {
    if (kontra === null) return [];
    const last = WORD_TOKENS.indexOf(kontra.word);
    return [
        ...WORD_TOKENS.slice(0, last + 1).map((word, index) =>
            words["result.wordFactor"]({
                word: WORD_TEXTS[word],
                factor: String(index === last ? kontra.factor : 2 ** (index + 1)),
            }),
        ),
        ...bockWordOf(bock_factor),
    ];
}

function chipsOf(result: Result): Chip[] {
    const factor = result.kontra === null ? bockWordOf(result.bock_factor).map((word) => ({ word, ticked: true })) : [];
    if (result.matadors === null) return factor;
    const { count, mit } = result.matadors;
    const matadors = mit ? words["result.matadorsWith"](count) : words["result.matadorsWithout"](count);
    return [
        { word: matadors, ticked: false },
        ...result.levels.map((level) => ({ word: LEVEL_WORDS[level], ticked: true })),
        ...factor,
    ];
}

// The value stands as a product when a step after it changes the score: the lost game's doubling or the Bock factor.
function equationOf(result: Result): Equation | null {
    const product = result.doubled || result.bock_factor > 1 ? result.game_value : null;
    if (result.multiplier === null && product === null) return null;
    return { multiplier: result.multiplier, base: result.base_value, product };
}

function listLineOf(result: Result, sides: SideNames): ListLine {
    const declarerGain = (result.gains.find((one) => one.seat === result.declarer_seat) as SeatGain).gain;
    const opponentGain = result.gains.find((one) => one.seat !== result.declarer_seat) as SeatGain;
    const score = signed(result.score);
    return {
        side: sides.declarer,
        steps: [
            result.kontra === null
                ? words["result.listGame"]({ score })
                : words["result.listGameWord"]({ word: WORD_TEXTS[result.kontra.word], score }),
            words["result.listBonus"]({ bonus: signed(result.list_bonus) }),
            `= ${signed(declarerGain)}`,
        ],
        share: result.doubled
            ? words["result.share"]({ opponents: sides.opponents, gain: signed(opponentGain.gain) })
            : null,
    };
}

export function declaredResult(table: Table): Result | null {
    return table.result?.kind === "declared" ? table.result : null;
}

// The ordinal of the declared result that the update brings to a page that watches; a page that opens later or
// reconnects sees the result as it stands, so it has none.
export function resultJustAppeared(previous: Table | undefined, next: Table): number | null {
    const result = declaredResult(next);
    if (previous === undefined || next.version <= previous.version || result === null) return null;
    return previous.result?.ordinal === result.ordinal ? null : result.ordinal;
}

// A give-up is the ending that decided the game, so its stamp stands where an overbid game's would.
function stampOf(result: Result, chairs: readonly Chair[]): Stamp | null {
    if (result.ending === "given-up") {
        const giver = nameOf(chairs, result.ended_by_seat as number) ?? "";
        return { word: words["result.givenUp"], face: giver.slice(0, 1) };
    }
    return result.overbid ? { word: words["result.overbid"], face: null } : null;
}

// The card reads only what the server counted: the sides, the ticks and the glow follow its answer.
export function resultView(table: Table): ResultView {
    const result = declaredResult(table) as Result;
    const { chairs } = table;
    const own = chairs.find((chair) => chair.is_mine);
    const isDeclarer = own?.seat === result.declarer_seat;
    const declarerName = nameOf(chairs, result.declarer_seat) ?? "";
    const sides = sideNames(chairs, result.declarer_seat);
    const good = own === undefined ? result.won : (result.gains.find((one) => one.seat === own.seat) as SeatGain).won;
    let word: string;
    if (own === undefined) {
        word = result.won
            ? words["result.declarerWins"]({ name: declarerName })
            : words["result.declarerLoses"]({ name: declarerName });
    } else word = good ? words["result.won"] : words["result.lost"];
    const name = gameLabel(result).name;
    return {
        word,
        good,
        suit: isSuitGame(result.game) ? result.game : null,
        gameWord: result.game === "null" ? name : gameWord(result.game),
        gameLine:
            own !== undefined && !isDeclarer
                ? words["result.opponentGameLine"]({ declarer: declarerName, game: name })
                : name,
        missed: result.announcement_missed ? MISSED_WORDS[result.announcement] : null,
        chips: chipsOf(result),
        doublings: doublingsOf(result),
        equation: equationOf(result),
        stamp: stampOf(result, chairs),
        raise: result.overbid
            ? words["result.raise"]({
                  value: String(result.game_value),
                  bid: String(result.bid),
                  settled: String(result.settled_value),
              })
            : null,
        doubled: result.doubled,
        score: signed(result.score),
        list: listLineOf(result, sides),
        sides,
        points:
            result.game === "null" ? null : { declarer: result.declarer_points, opponents: result.opponents_points },
        snug: result.overbid || result.levels.length > SNUG_LEVELS || result.kontra !== null,
        rows: reckoningRows(chairs, result.gains),
    };
}

// The coasters: each seat's gain with the viewer's own chair first.
function reckoningRows(chairs: readonly Chair[], gains: readonly SeatGain[]): ReckoningRow[] {
    return ownFirst(chairs).map(({ seat, is_mine }) => {
        const { gain, won } = gains.find((one) => one.seat === seat) as SeatGain;
        return {
            seat,
            initial: (nameOf(chairs, seat) ?? "").slice(0, 1),
            name: is_mine ? words["result.sideYou"] : nameOf(chairs, seat),
            gain,
            gainText: gain > 0 ? signed(gain) : withMinus(gain),
            won,
        };
    });
}

function pushChip(result: RamschResult): string[] {
    if (result.pushes === 0) return [];
    return [
        result.push_factor === 1
            ? words["push.timesFlat"]({ count: result.pushes })
            : words["push.times"]({ count: result.pushes, factor: String(result.push_factor) }),
    ];
}

function ramschHead(
    result: RamschResult,
    chairs: readonly Chair[],
    strong: readonly RamschSeat[],
): Pick<RamschView, "word" | "mark" | "lost"> {
    const own = chairs.find((chair) => chair.is_mine);
    if (result.durchmarsch_seat !== null) {
        return own?.seat === result.durchmarsch_seat
            ? { word: words["result.won"], mark: "tick", lost: false }
            : { word: words["result.durchmarsch"], mark: null, lost: false };
    }
    if (strong.some((one) => one.seat === own?.seat)) return { word: words["result.lost"], mark: "cross", lost: true };
    const names = strong.map((one) => shownName(chairs, one.seat));
    return {
        word:
            names.length === 1
                ? words["result.loses"]({ name: names[0] as string })
                : words["result.losesTogether"]({ names: listFormat.format(names) }),
        mark: null,
        lost: false,
    };
}

// The card reads the answer's counts and never reckons a score: the sweeper's or the losers' score is the value.
export function ramschResultView(table: Table): RamschView | null {
    const result = table.result;
    if (result?.kind !== "ramsch") return null;
    const { chairs } = table;
    const sweeper = result.seats.find((one) => one.seat === result.durchmarsch_seat);
    const strong = sweeper === undefined ? result.seats.filter((one) => one.score < 0) : [sweeper];
    const lead = strong[0] as RamschSeat;
    return {
        ...ramschHead(result, chairs, strong),
        eyes: words["result.eyes"]({ points: String(lead.points) }),
        chips: [
            ...(result.divided_by_ten ? [words["result.byTen"]] : []),
            ...pushChip(result),
            ...(result.jungfrau ? [words["result.jungfrau"]] : []),
            ...bockWordOf(result.bock_factor),
        ],
        score: signed(lead.score),
        loss: sweeper === undefined,
        counts: ownFirst(chairs).map(({ seat, is_mine }) => ({
            seat,
            name: is_mine ? words["result.sideYou"] : shownName(chairs, seat),
            points: (result.seats.find((one) => one.seat === seat) as RamschSeat).points,
            strong: strong.some((one) => one.seat === seat),
        })),
        rows: reckoningRows(
            chairs,
            result.seats.map(({ seat, score }) => ({ seat, gain: score, won: score > 0 })),
        ),
    };
}

// Whoever has not tapped, and whoever is away even after tapping: the next hand waits for their return.
export function awaitedNames(chairs: readonly Chair[]): string[] {
    return chairs.flatMap((chair) =>
        chair.occupant_name !== null && (!chair.ready || chair.is_away) ? [chair.occupant_name] : [],
    );
}

// A seated viewer taps until their own chair is ready, then waits for the others by name. Ready with nobody
// awaited while the result still stands means the deal after the last tap failed: the button stays so a tap asks again.
export function weiterBar(table: Table): WeiterBar | null {
    const own = table.chairs.find((chair) => chair.is_mine);
    if (own === undefined || table.result === null) return null;
    const awaited = awaitedNames(table.chairs);
    if (!own.ready) return { kind: "tap", again: false };
    if (awaited.length === 0) return { kind: "tap", again: true };
    return { kind: "wait", text: words["table.waitingFor"]({ names: listFormat.format(awaited) }) };
}
