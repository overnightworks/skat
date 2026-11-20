import {
    CALL_CHANNEL_VERSION,
    OK_STATUS,
    PERSON_KEY,
    isPlainObject,
    type CallHost,
    type Corners,
    type SeatEntry,
    type SeatsMessage,
} from "#lib/callFrame.ts";
import { CHAIRS_PER_TABLE, TABLES_PATH, TABLE_PERSON_KEYS_SUFFIX } from "#lib/wire.ts";

// The pure decisions of the seats a framed table tells its call: which tile boxes go out, which chairs are see-through
// and when the table holds back. `CallSeats.svelte` reads the page, runs the frames and writes the clip paths by them.

/** The farthest a backdrop paints beyond its box, rim and drop shadow of the felt included, with room to spare. */
const OUTER_MARGIN = 96;

/** The person key of each occupied chair of a table at one version. */
export interface SeatKeys {
    readonly version: number;
    readonly keys: ReadonlyMap<number, string>;
}

function seatKeyOf(entry: unknown): readonly [number, string] | null {
    if (!isPlainObject(entry)) return null;
    const { seat, key } = entry;
    if (typeof seat !== "number" || !Number.isSafeInteger(seat)) return null;
    return typeof key === "string" && PERSON_KEY.test(key) ? [seat, key] : null;
}

function seatKeysOf(body: unknown): SeatKeys | null {
    if (!isPlainObject(body)) return null;
    const { version, keys } = body;
    if (typeof version !== "number" || !Number.isSafeInteger(version) || !Array.isArray(keys)) return null;
    if (keys.length > CHAIRS_PER_TABLE) return null;
    const bySeat = new Map<number, string>();
    for (const entry of keys) {
        const seatKey = seatKeyOf(entry);
        if (seatKey === null || bySeat.has(seatKey[0])) return null;
        bySeat.set(seatKey[0], seatKey[1]);
    }
    return { version, keys: bySeat };
}

/** The table's person keys from the signed-in route; anything but a 200 with the checked shape counts as no keys. */
export async function readPersonKeys(fetchRoute: CallHost["fetch"], tableId: string): Promise<SeatKeys | null> {
    try {
        const answer = await fetchRoute(`${TABLES_PATH}/${tableId}${TABLE_PERSON_KEYS_SUFFIX}`);
        return answer.status === OK_STATUS ? seatKeysOf(await answer.json()) : null;
    } catch {
        return null;
    }
}

/** What the page read of one chair's tile in one frame, the browser's numbers unchanged. */
export interface TileReading {
    readonly seat: number;
    /** The chair's person key when it is current, else undefined. */
    readonly key: string | undefined;
    /** What the chair held when it was read: `occupancyOf` its view. */
    readonly occupancy: string;
    readonly rect: { readonly x: number; readonly y: number; readonly width: number; readonly height: number };
    /** The tile's `--call-tile-shape`. */
    readonly shape: string;
    /** The tile's computed corner radii. */
    readonly radii: Corners;
}

/** A chair of the last posted `seats`, with what it held when it was posted. */
export interface PostedSeat {
    readonly seat: number;
    readonly occupancy: string;
    readonly entry: SeatEntry;
}

const isFiniteNumber = (value: number): boolean => Number.isFinite(value);
const isCorner = (value: number): boolean => Number.isFinite(value) && value >= 0;

function entryOf(tile: TileReading): SeatEntry | null {
    const { key, rect, shape, radii } = tile;
    if (key === undefined) return null;
    if (![rect.x, rect.y].every(isFiniteNumber)) return null;
    if (![rect.width, rect.height].every((side) => Number.isFinite(side) && side > 0)) return null;
    const box = { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
    if (shape === "round") return { key, box, shape };
    if (shape === "rect" && Object.values(radii).every(isCorner)) return { key, box, shape, radius: radii };
    return null;
}

/** The chairs whose tile read as a valid entry, in seat order and at most one per chair of the table. */
export function postedSeats(tiles: readonly TileReading[]): PostedSeat[] {
    return tiles
        .toSorted((first, second) => first.seat - second.seat)
        .flatMap((tile) => {
            const entry = entryOf(tile);
            return entry === null ? [] : [{ seat: tile.seat, occupancy: tile.occupancy, entry }];
        })
        .slice(0, CHAIRS_PER_TABLE);
}

export function seatsMessage(tableId: string, seats: readonly PostedSeat[]): SeatsMessage {
    return { v: CALL_CHANNEL_VERSION, type: "seats", table: tableId, seats: seats.map(({ entry }) => entry) };
}

function cornerPath(box: SeatEntry["box"], corners: Corners): string {
    // A box scales corners that do not fit a side down together, as the browser draws them.
    const scale = Math.min(
        1,
        box.w / (corners.tl + corners.tr),
        box.w / (corners.bl + corners.br),
        box.h / (corners.tl + corners.bl),
        box.h / (corners.tr + corners.br),
    );
    const [tl, tr, br, bl] = [corners.tl, corners.tr, corners.br, corners.bl].map((corner) => corner * scale) as [
        number,
        number,
        number,
        number,
    ];
    const { x, y, w, h } = box;
    return [
        `M ${String(x + tl)} ${String(y)}`,
        `H ${String(x + w - tr)}`,
        `A ${String(tr)} ${String(tr)} 0 0 1 ${String(x + w)} ${String(y + tr)}`,
        `V ${String(y + h - br)}`,
        `A ${String(br)} ${String(br)} 0 0 1 ${String(x + w - br)} ${String(y + h)}`,
        `H ${String(x + bl)}`,
        `A ${String(bl)} ${String(bl)} 0 0 1 ${String(x)} ${String(y + h - bl)}`,
        `V ${String(y + tl)}`,
        `A ${String(tl)} ${String(tl)} 0 0 1 ${String(x + tl)} ${String(y)}`,
        "Z",
    ].join(" ");
}

function ellipsePath(box: SeatEntry["box"]): string {
    const [radiusX, radiusY] = [box.w / 2, box.h / 2].map(String) as [string, string];
    const centerY = String(box.y + box.h / 2);
    const [left, right] = [String(box.x), String(box.x + box.w)];
    const arc = `A ${radiusX} ${radiusY} 0 1 0`;
    return `M ${left} ${centerY} ${arc} ${right} ${centerY} ${arc} ${left} ${centerY} Z`;
}

/**
 * A clip path that keeps all of the element and its rim and shadow but the holes: an outer rectangle and one rounded
 * rectangle or ellipse per hole, cut out by the even-odd rule. It is written in the element's own coordinates, so a
 * hole is the tile's box less the element's top-left corner.
 */
export function holesPath(
    owner: { readonly left: number; readonly top: number; readonly width: number; readonly height: number },
    holes: readonly SeatEntry[],
): string {
    const outer = [
        `M ${String(-OUTER_MARGIN)} ${String(-OUTER_MARGIN)}`,
        `H ${String(owner.width + OUTER_MARGIN)}`,
        `V ${String(owner.height + OUTER_MARGIN)}`,
        `H ${String(-OUTER_MARGIN)}`,
        "Z",
    ].join(" ");
    const cuts = holes.map((hole) => {
        const local = { ...hole.box, x: hole.box.x - owner.left, y: hole.box.y - owner.top };
        return hole.shape === "round" ? ellipsePath(local) : cornerPath(local, hole.radius);
    });
    return `path(evenodd, "${[outer, ...cuts].join(" ")}")`;
}

/** What a chair of the table view holds, as far as a person key can go stale: who sits, of which kind, and whether it is mine. */
export function occupancyOf(chair: {
    readonly occupant_name: string | null;
    readonly occupant_kind: string | null;
    readonly is_mine: boolean;
}): string {
    return JSON.stringify([chair.occupant_name, chair.occupant_kind, chair.is_mine]);
}

/**
 * Whether the table posts, holds back or tells the call that the keys failed: a failed read posts an empty list; keys
 * of another version than the view are not posted and leave the call its last layout.
 */
export type Hold = "failed" | "held" | "current";

export function holdOf(failed: boolean, keys: SeatKeys | null, viewVersion: number | null): Hold {
    if (failed) return "failed";
    return keys !== null && keys.version === viewVersion ? "current" : "held";
}

/** The keys of a `placed` that the last posted `seats` carries; any other key is ignored on its own. */
export function acceptedPlacements(keys: readonly string[], posted: readonly PostedSeat[]): ReadonlySet<string> {
    const postedKeys = new Set(posted.map(({ entry }) => entry.key));
    return new Set(keys.filter((key) => postedKeys.has(key)));
}

/**
 * The chairs that are see-through: the key is in the placed set and in the last posted `seats` entry for that chair, and
 * the chair still holds who it held when it was posted. A hole stays shut unless the keys are those of the view's version.
 */
export function openSeats(state: {
    readonly posted: readonly PostedSeat[];
    readonly placed: ReadonlySet<string>;
    readonly occupancyNow: ReadonlyMap<number, string>;
    readonly current: boolean;
}): PostedSeat[] {
    if (!state.current) return [];
    return state.posted.filter(
        ({ seat, occupancy, entry }) => state.placed.has(entry.key) && state.occupancyNow.get(seat) === occupancy,
    );
}
