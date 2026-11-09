import { words } from "#lib/words.ts";
import { sideNames, type SideNames } from "#lib/playView.ts";
import type { Chair, Game, Sides, Table } from "../routes/(start)/tables.ts";

export type ReckoningRow = { seat: number; name: string | null; gain: number; winner: boolean };
export type ResultView = {
    word: string;
    // The mark's shape: a tick when the word is good news for this viewer, a cross when it is not.
    good: boolean;
    game: Game;
    // An opponent's game line names whose game it was.
    byName: string | null;
    // The line under the stamp: what the game was worth against what was bid.
    miss: string | null;
    // Only the declarer carries a score, signed.
    score: string | null;
    sides: SideNames;
    points: Sides;
    rows: ReckoningRow[];
};
export type WeiterBar = { kind: "tap" } | { kind: "wait"; names: string };

const MINUS = "−";

function signed(score: number): string {
    return score < 0 ? `${MINUS}${String(-score)}` : `+${String(score)}`;
}

function nameOf(chairs: readonly Chair[], seat: number): string | null {
    return (chairs.find((chair) => chair.seat === seat) as Chair).occupant_name;
}

// The viewer's own chair comes first, then the others in seat order; a watcher has no own chair.
function ownFirst(chairs: readonly Chair[]): Chair[] {
    const own = chairs.filter((chair) => chair.is_mine);
    return [...own, ...chairs.filter((chair) => !chair.is_mine)];
}

// The card reads only what the server counted: the sides follow from who declared and who won.
export function resultView(table: Table): ResultView {
    const result = table.result as NonNullable<Table["result"]>;
    const { chairs } = table;
    const own = chairs.find((chair) => chair.is_mine);
    const isDeclarer = own?.seat === result.declarer_seat;
    const declarerName = nameOf(chairs, result.declarer_seat) ?? "";
    const sides = sideNames(chairs, result.declarer_seat);
    const good = own === undefined || isDeclarer ? result.won : !result.won;
    let word: string;
    if (own === undefined) word = `${declarerName} ${result.won ? words.resultWins : words.resultLoses}`;
    else word = good ? words.resultWon : words.resultLost;
    return {
        word,
        good,
        game: result.game,
        byName: own !== undefined && !isDeclarer ? declarerName : null,
        miss: result.overbid
            ? `${words.gameWorth} ${String(result.game_value)} < ${words.bidValue} ${String(result.bid)}`
            : null,
        score: isDeclarer ? signed(result.score) : null,
        sides: isDeclarer ? { declarer: words.sideYou, opponents: words.sideThem } : sides,
        points: { declarer: result.declarer_points, opponents: result.opponents_points },
        rows: ownFirst(chairs).map(({ seat }) => ({
            seat,
            name: nameOf(chairs, seat),
            gain: (result.gains.find((gain) => gain.seat === seat) as { gain: number }).gain,
            winner: (seat === result.declarer_seat) === result.won,
        })),
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
    if (!own.ready || awaited.length === 0) return { kind: "tap" };
    return { kind: "wait", names: awaited.join(` ${words.and} `) };
}
