import { words } from "#lib/words.ts";
import { sideNames, type SideNames } from "#lib/playView.ts";
import {
    gameLabel,
    gameWord,
    isSuitGame,
    type Announcement,
    type Chair,
    type Level,
    type Result,
    type Sides,
    type SeatGain,
    type Suit,
    type Table,
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
    equation: Equation | null;
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
// `again` marks a tap that asks for a deal that failed: it stays tappable however often it is tapped.
export type WeiterBar = { kind: "tap"; again: boolean } | { kind: "wait"; names: string };

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

function chipsOf(result: Result): Chip[] {
    if (result.matadors === null) return [];
    const { count, mit } = result.matadors;
    const matadors = mit ? words["result.matadorsWith"](count) : words["result.matadorsWithout"](count);
    return [
        { word: matadors, ticked: false },
        ...result.levels.map((level) => ({ word: LEVEL_WORDS[level], ticked: true })),
    ];
}

function equationOf(result: Result): Equation | null {
    const product = result.doubled ? result.game_value : null;
    if (result.multiplier === null && product === null) return null;
    return { multiplier: result.multiplier, base: result.base_value, product };
}

function listLineOf(result: Result, sides: SideNames): ListLine {
    const declarerGain = (result.gains.find((one) => one.seat === result.declarer_seat) as SeatGain).gain;
    const opponentGain = result.gains.find((one) => one.seat !== result.declarer_seat) as SeatGain;
    return {
        side: sides.declarer,
        steps: [
            words["result.listGame"]({ score: signed(result.score) }),
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

// The card reads only what the server counted: the sides, the ticks and the glow follow its answer.
export function resultView(table: Table): ResultView {
    const result = declaredResult(table) as Result;
    const { chairs } = table;
    const own = chairs.find((chair) => chair.is_mine);
    const isDeclarer = own?.seat === result.declarer_seat;
    const declarerName = nameOf(chairs, result.declarer_seat) ?? "";
    const sides = sideNames(chairs, result.declarer_seat);
    const shownSides = isDeclarer ? { declarer: words["result.sideYou"], opponents: words["result.sideThem"] } : sides;
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
        equation: equationOf(result),
        raise: result.overbid
            ? words["result.raise"]({
                  value: String(result.game_value),
                  bid: String(result.bid),
                  settled: String(result.settled_value),
              })
            : null,
        doubled: result.doubled,
        score: signed(result.score),
        list: listLineOf(result, shownSides),
        sides: shownSides,
        points:
            result.game === "null" ? null : { declarer: result.declarer_points, opponents: result.opponents_points },
        snug: result.overbid || result.levels.length > SNUG_LEVELS,
        rows: ownFirst(chairs).map(({ seat }) => {
            const { gain, won } = result.gains.find((one) => one.seat === seat) as SeatGain;
            return {
                seat,
                initial: (nameOf(chairs, seat) ?? "").slice(0, 1),
                name: seat === own?.seat ? words["result.sideYou"] : nameOf(chairs, seat),
                gain,
                gainText: gain > 0 ? signed(gain) : withMinus(gain),
                won,
            };
        }),
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
    return { kind: "wait", names: awaited.join(` ${words["result.and"]} `) };
}
