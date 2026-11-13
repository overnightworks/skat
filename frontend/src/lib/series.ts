import { faceOf, type AskButton, type AskView } from "#lib/giveUp.ts";
import { LEVEL_WORDS, withMinus } from "#lib/result.ts";
import { listFormat, words } from "#lib/words.ts";
import { gameLabel, type SeriesEndAnswer, type SeriesEntry, type Table } from "../routes/(start)/tables.ts";

// The series as the table answers it: the page counts, asks and ranks what the server decided and decides no rule.
export function seriesOver(table: Table): boolean {
    return table.series?.over === true;
}

// The quiet mark on the felt; none before the first deal and none once the standings take its place.
export function seriesCountText(table: Table): string | null {
    const series = table.series;
    if (series === null || series.over || series.game_number === 0) return null;
    return words["table.seriesCount"]({ game: String(series.game_number), count: String(series.game_count) });
}

const SERIES_END_BUTTONS: AskButton<SeriesEndAnswer>[] = [
    { answer: "agree", word: words["table.yes"], icon: "check", primary: true },
    { answer: "refuse", word: words["table.no"], icon: "cross", primary: false },
];

// The plaque of a standing proposal to end the series: the other two see Ja and Nein, whoever proposed or said yes waits
// for the rest by name, and a watcher is told who proposed.
export function seriesEndAsk(table: Table): AskView<SeriesEndAnswer> | null {
    const proposal = table.series?.end_proposal;
    if (!proposal) return null;
    const viewerSeat = table.chairs.find((chair) => chair.is_mine)?.seat;
    const answeredSeats = [proposal.proposer_seat, proposal.accepter_seat];
    const waitingFor = table.chairs.filter((chair) => !answeredSeats.includes(chair.seat));
    if (viewerSeat !== undefined && answeredSeats.includes(viewerSeat)) {
        const faces = waitingFor.map((chair) => faceOf(table.chairs, chair.seat));
        const names = listFormat.format(faces.map((face) => face.name));
        return { text: words["table.waitingFor"]({ names }), faces, waits: true, buttons: [] };
    }
    const proposer = faceOf(table.chairs, proposal.proposer_seat);
    return {
        text: words["table.wantsToEndSeries"]({ name: proposer.name }),
        faces: [proposer],
        waits: false,
        buttons: viewerSeat === undefined ? [] : SERIES_END_BUTTONS,
    };
}

// The key that proposes the end: a seated member between two games, when no proposal stands.
export function seriesEndOffered(table: Table): boolean {
    const series = table.series;
    if (series === null || series.over || series.game_number === 0 || series.end_proposal !== null) return false;
    return table.hand === null && table.chairs.some((chair) => chair.is_mine);
}

export type StandingRow = {
    place: number;
    name: string;
    initial: string;
    total: string;
    record: string;
    winner: boolean;
    // Left the series: no chair of the table is theirs any more.
    gone: boolean;
};
export type StandingsView = {
    heading: string;
    sub: string;
    rows: StandingRow[];
    // The chairs of whoever stands first, which the table marks.
    winnerSeats: ReadonlySet<number>;
};

const FIRST_PLACE = 1;

// The end of the series: every account of its list ranked as the server ranked it; the same for every viewer.
export function standingsView(table: Table): StandingsView | null {
    const series = table.series;
    if (series?.standings == null) return null;
    const seated = new Map(
        table.chairs.flatMap((chair) =>
            chair.occupant_name === null ? [] : [[chair.occupant_name, chair.seat] as const],
        ),
    );
    const rows = series.standings.map((standing) => {
        const name = standing.display_name ?? words["table.seriesNameless"];
        return {
            place: standing.place,
            name,
            initial: name.slice(0, 1),
            total: withMinus(standing.total),
            record: words["table.seriesRecord"]({ won: String(standing.won), lost: String(standing.lost) }),
            winner: standing.place === FIRST_PLACE,
            gone: !seated.has(name),
        };
    });
    const winnerSeats = new Set(rows.filter((row) => row.winner).flatMap((row) => seated.get(row.name) ?? []));
    return {
        heading: words["table.seriesEnded"],
        sub: words["table.seriesGames"](series.game_number),
        rows,
        winnerSeats,
    };
}

export type GameRow = {
    number: number;
    name: string;
    initial: string;
    // The game and its levels; a Ramsch says how often its skat was pushed, and a Ramsch with no push has none.
    line: string | null;
    value: string;
    gain: string;
    lost: boolean;
};

const PLAIN_LEVELS = new Set(["spiel", "hand", "ouvert"]);

function signed(score: number): string {
    return score < 0 ? withMinus(score) : `+${String(score)}`;
}

function nameOrNobody(name: string | null): string {
    return name ?? words["table.seriesNameless"];
}

function declaredRow(entry: Extract<SeriesEntry, { kind: "declared" }>): GameRow {
    const name = nameOrNobody(entry.declarer_name);
    const levels = entry.levels.filter((level) => !PLAIN_LEVELS.has(level)).map((level) => LEVEL_WORDS[level]);
    return {
        number: entry.number,
        name,
        initial: name.slice(0, 1),
        line: [gameLabel(entry).name, ...levels].join(", "),
        value: String(entry.settled_value),
        gain: signed(entry.score),
        lost: entry.score < 0,
    };
}

// A Ramsch has no declarer: its row names whoever it cost the most, or whoever swept it, and what it cost or gained.
function ramschRow(entry: Extract<SeriesEntry, { kind: "ramsch" }>): GameRow {
    const scores = entry.seats.map((seat) => seat.score);
    const score = entry.durchmarsch ? Math.max(...scores) : Math.min(...scores);
    const subjects = entry.seats.filter((seat) => seat.score === score).map((seat) => nameOrNobody(seat.name));
    return {
        number: entry.number,
        name: words["table.seriesRamschOf"]({ name: listFormat.format(subjects) }),
        initial: (subjects[0] as string).slice(0, 1),
        line: entry.pushes === 0 ? null : words["table.seriesPushed"]({ count: String(entry.pushes) }),
        value: "",
        gain: signed(score),
        lost: score < 0,
    };
}

// The newest game on top; a passed-in hand has no row because the server lists none.
export function gameRows(entries: readonly SeriesEntry[]): GameRow[] {
    return entries.map((entry) => (entry.kind === "declared" ? declaredRow(entry) : ramschRow(entry))).reverse();
}
