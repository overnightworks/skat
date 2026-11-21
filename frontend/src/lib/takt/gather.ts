import type { Card } from "../../routes/(start)/tables.ts";
import { drawnFrom, type Aloft } from "./aloft.ts";
import { gripStoppingWithin, thrownAt, type Throw } from "./land.ts";
import { cardFork } from "./seed.ts";
import { mix, phase, type Place, type Pose, type Timeline, type Track } from "./timeline.ts";

/** How a motion set rests, lifts and gathers a finished trick. */
export interface GatherSet {
    /** How long the trick lies still once its last card lies. */
    readonly restSeconds: number;
    /** How long it lies before the card that took it lifts. */
    readonly liftAfterSeconds: number;
    /** How high the taking card lifts, in card widths. */
    readonly rise: number;
    /** Whether the lift springs and the trick is pushed to a heap, turned over and thrown; else it glides open in one move. */
    readonly springs: boolean;
    /** How long the cards take to come together in the middle. */
    readonly gatherSeconds: number;
    /** From the gathered trick to the instant it lies on its taker's pile. */
    readonly glideSeconds: number;
    /** How much longer the last trick of a hand stands lifted before it is gathered; its result waits for it. */
    readonly lastHoldSeconds: number;
}

/** One card of a finished trick: where it lies, as the page measured it, and whether it took the trick. */
export interface Gathered {
    readonly card: Card;
    readonly lies: Place;
    readonly takes: boolean;
}

/**
 * A finished trick between the places the page measured: its cards in the order they were played, where they come
 * together, and the pile's top card.
 */
export interface Gathering {
    readonly cards: readonly Gathered[];
    readonly middle: { readonly x: number; readonly y: number };
    readonly pile: Place;
}

export interface LiftTracks {
    readonly card: Track<Pose>;
    readonly shade: Track<Pose>;
    /** How much of the brass rim shows. */
    readonly rim: Track<number>;
    /** The seal a deciding trick's card carries, pressed onto its rim. */
    readonly seal: Track<Pose>;
}

export interface CardTracks {
    readonly card: Track<Pose>;
    readonly shade: Track<Pose>;
    /** How much of the card's back shows. */
    readonly rear: Track<number>;
    readonly rim: Track<number>;
    /** How much of the player's name shows, which stays where the card lay. */
    readonly name: Track<number>;
}

export interface GatherTracks {
    readonly cards: readonly CardTracks[];
    /** How much of the pile's top card shows, which the trick becomes. */
    readonly pile: Track<number>;
}

export interface TakerTracks {
    /** How much of the gold ring round the taker's chair shows. */
    readonly flash: Track<number>;
    /** The chair's hop, which only a set that springs has. */
    readonly hop: Track<Pose> | null;
}

// The taking card comes up toward the eye: it rises a little while its shade falls away below it by this share of its
// height, so it covers little of the names beside it.
const SHADE_FALLS = 0.65;
const LIFT_SWELLS = 0.06;
const LIFT_EASES_SECONDS = 0.16;
const LIFT_SPRING = { hertz: 3.5, damping: 0.5 };
const RIM_APPEARS_SECONDS = 0.12;
// A seal is pressed on once the rim shows: it comes down from this size, and gives way as it hits in a set that springs.
const SEAL_PRESSED_SECONDS = 0.18;
const SEAL_FROM = 1.9;
const SEAL_GIVES = 0.14;
const SEAL_GIVE_FADES_PER_SECOND = 20;
const LIFT_SETTLES_SECONDS = 0.6;
// A heap is untidy: each card ends this far off the middle, in card widths, and turned by up to these degrees.
const HEAP_REACH = 0.1;
const HEAP_TURN_DEGREES = 22;
const HEAP_SPRING = { hertz: 4, damping: 0.8 };
const HEAP_STAGGER_SECONDS = 0.04;
// A heap is squared up while it is turned over: its cards close in by this share, and fan by these degrees once
// their backs are up.
const PACKET_CLOSES = 0.5;
const PACKET_FANS_DEGREES = 9;
const TURN_OVER_SHARE = 0.28;
const TURN_OVER_LIFT = 0.12;
const TURN_OVER_SWELLS = 0.05;
// The turned heap is thrown onto the pile for this share of the glide and slides the rest, each card a little after
// the one below it and carried a little further round.
const FLIGHT_SHARE = 0.42;
const THROW_STAGGER_SECONDS = 0.02;
const THROW: Omit<Throw, "flightSeconds" | "grip"> = { lift: 0.14, swell: 0.05, ease: 0.5, squash: 0.03 };
const THROW_CARRY_DEGREES = 7;
// A trick becomes the pile's top card as it arrives: a thrown one within this long, one that glides open over this last
// share of its glide.
const STOPS_INTO_PILE_SECONDS = 0.03;
const FADES_INTO_PILE = 0.3;
const NAME_FADES_SECONDS = 0.1;
const RIM_FADES_SECONDS = 0.2;
const FLASH_RISES_SECONDS = 0.1;
const FLASH_STANDS_SECONDS = 0.15;
const FLASH_FADES_SECONDS = { springs: 0.9, glides: 0.3 };
const HOP_SECONDS = 0.3;
const HOP_PIXELS = 5;

const smooth = (share: number): number => share * share * (3 - 2 * share);

// A damped spring from 0 to 1 that starts at rest; a damping below 1 lets it swing past 1.
function spring(seconds: number, { hertz, damping }: { hertz: number; damping: number }): number {
    if (seconds <= 0) return 0;
    const speed = 2 * Math.PI * hertz;
    const swing = speed * Math.sqrt(1 - damping * damping);
    const left = Math.cos(swing * seconds) + ((damping * speed) / swing) * Math.sin(swing * seconds);
    return 1 - Math.exp(-damping * speed * seconds) * left;
}

function between(from: Aloft, to: Aloft, share: number): Aloft {
    return {
        x: mix(from.x, to.x, share),
        y: mix(from.y, to.y, share),
        up: mix(from.up, to.up, share),
        turn: mix(from.turn, to.turn, share),
        size: mix(from.size, to.size, share),
        facing: mix(from.facing, to.facing, share),
        shown: mix(from.shown, to.shown, share),
    };
}

const lying = (lies: Place): Aloft => ({ x: lies.x, y: lies.y, up: 0, turn: lies.turn, size: 1, facing: 1, shown: 1 });

// The taking card `up` of its way to the height it stands lifted at.
function lifted(set: GatherSet, lies: Place, up: number): Aloft {
    return {
        ...lying(lies),
        y: lies.y + SHADE_FALLS * set.rise * lies.width * up,
        up: set.rise * up,
        size: 1 + (set.springs ? LIFT_SWELLS : 0) * up,
    };
}

/**
 * The instants of a finished trick that need no measure, counted from when its last card lies: the card that took it
 * lifts, the trick is gathered, it glides from the middle, which sounds, and it is piled.
 */
export function gatherInstants(set: GatherSet): Readonly<Record<"lifts" | "gathers" | "glides" | "piled", number>> {
    const glides = set.restSeconds + set.gatherSeconds;
    return { lifts: set.liftAfterSeconds, gathers: set.restSeconds, glides, piled: glides + set.glideSeconds };
}

/** The card that took a trick lifts where it lies and shows its brass rim; a deciding trick's seal is pressed onto it. */
export function liftTimeline(set: GatherSet, lies: Place): Timeline<LiftTracks> {
    const up = (seconds: number): number =>
        set.springs ? spring(seconds, LIFT_SPRING) : 1 - (1 - phase(seconds, 0, LIFT_EASES_SECONDS)) ** 3;
    const pieces = (seconds: number) => drawnFrom(lies, lifted(set, lies, up(seconds)));
    const sealed = RIM_APPEARS_SECONDS + SEAL_PRESSED_SECONDS;
    return {
        seconds: LIFT_SETTLES_SECONDS,
        tracks: {
            card: (seconds) => pieces(seconds).card,
            shade: (seconds) => pieces(seconds).shade,
            rim: (seconds) => phase(seconds, 0, RIM_APPEARS_SECONDS),
            seal: (seconds) => {
                const pressed = phase(seconds, RIM_APPEARS_SECONDS, SEAL_PRESSED_SECONDS);
                const gives = set.springs && seconds >= sealed ? SEAL_GIVES : 0;
                const size =
                    mix(SEAL_FROM, 1, pressed ** 2) *
                    (1 - gives * Math.exp(-SEAL_GIVE_FADES_PER_SECOND * (seconds - sealed)));
                return { x: 0, y: 0, turn: 0, wide: size, tall: size, opacity: Math.min(1, pressed * 2) };
            },
        },
    };
}

// When the trick touches its taker's pile, counted from its first move.
function touchesAfter(set: GatherSet): number {
    const flown = set.springs ? TURN_OVER_SHARE + FLIGHT_SHARE : 1;
    return set.gatherSeconds + set.glideSeconds * flown;
}

// How much of the pile's top card the trick has become, which shows as much less of the trick.
function piled(set: GatherSet, at: number): number {
    const within = set.springs ? STOPS_INTO_PILE_SECONDS : set.glideSeconds * FADES_INTO_PILE;
    return phase(at, set.gatherSeconds + set.glideSeconds - within, within);
}

type Way = (seconds: number) => Aloft;

const takerOf = (cards: readonly Gathered[]): Gathered => cards.find(({ takes }) => takes) as Gathered;

// The pile's top card as `gathered` comes to lie on it, turned the shorter way from `turn`.
function onPile({ pile }: Gathering, { lies }: Gathered, turn: number): Aloft {
    return { ...lying(pile), turn: turn + ((pile.turn - turn + 540) % 360) - 180, size: pile.width / lies.width };
}

function heapOf(seed: string, { middle }: Gathering, { card, lies }: Gathered): Aloft {
    const heap = cardFork(seed, card, "heap");
    return {
        ...lying(lies),
        x: middle.x + lies.width * heap.between(-HEAP_REACH, HEAP_REACH),
        y: middle.y + lies.width * heap.between(-HEAP_REACH, HEAP_REACH),
        turn: heap.between(-HEAP_TURN_DEGREES, HEAP_TURN_DEGREES),
    };
}

// A set that springs pushes a card onto the heap, squares the heap while it turns it over, and throws it onto the pile.
function sprungWay(set: GatherSet, seed: string, gathering: Gathering, gathered: Gathered): Way {
    const { cards, middle } = gathering;
    const turnOverSeconds = set.glideSeconds * TURN_OVER_SHARE;
    const flightSeconds = set.glideSeconds * FLIGHT_SHARE;
    const slideSeconds =
        set.glideSeconds - turnOverSeconds - flightSeconds - (cards.length - 1) * THROW_STAGGER_SECONDS;
    const thrown: Throw = { ...THROW, flightSeconds, grip: gripStoppingWithin(slideSeconds) };
    // The card that took the trick is gathered last and thrown last, the others in the order they were played.
    const turnOf = gathered.takes ? cards.length - 1 : cards.filter(({ takes }) => !takes).indexOf(gathered);
    const starts = gathered.takes ? lifted(set, gathered.lies, 1) : lying(gathered.lies);
    const heap = heapOf(seed, gathering, gathered);
    // A card swings past its place in the heap, never below the felt.
    const heapedAt = (at: number): Aloft => {
        const pushed = spring(at - turnOf * HEAP_STAGGER_SECONDS, HEAP_SPRING);
        return { ...between(starts, heap, pushed), up: mix(starts.up, 0, Math.min(1, pushed)) };
    };
    const heaped = heapedAt(set.gatherSeconds);
    const squared: Aloft = {
        ...heaped,
        x: mix(heaped.x, middle.x, PACKET_CLOSES),
        y: mix(heaped.y, middle.y, PACKET_CLOSES),
        turn: heapOf(seed, gathering, takerOf(cards)).turn * PACKET_CLOSES,
    };
    const packet: Aloft = { ...squared, turn: squared.turn + (turnOf - 1) * PACKET_FANS_DEGREES };
    const lands = onPile(gathering, gathered, packet.turn);
    const start = { turn: packet.turn - lands.turn, size: 1 / lands.size };
    return (at) => {
        if (at <= set.gatherSeconds) return heapedAt(at);
        const over = phase(at, set.gatherSeconds, turnOverSeconds);
        if (over < 1) {
            const air = Math.sin(Math.PI * over);
            // Cards turned apart would cross while they stand on edge.
            const turning =
                over < 0.5
                    ? between(heaped, squared, smooth(over * 2))
                    : between(squared, packet, smooth(over * 2 - 1));
            return {
                ...turning,
                up: TURN_OVER_LIFT * air,
                size: 1 + TURN_OVER_SWELLS * air,
                facing: Math.cos(Math.PI * over),
            };
        }
        const since = at - set.gatherSeconds - turnOverSeconds - turnOf * THROW_STAGGER_SECONDS;
        const { ahead, up, turn, size } = thrownAt(thrown, start, THROW_CARRY_DEGREES * (1 - turnOf), since);
        return {
            x: mix(lands.x, packet.x, ahead),
            y: mix(lands.y, packet.y, ahead),
            up,
            turn: lands.turn + turn,
            size: size * lands.size,
            facing: -1,
            shown: 1 - piled(set, at),
        };
    };
}

// Any other set lets the taking card go straight to the pile, and every other card joins its way; all fade into the pile.
function openWay(set: GatherSet, gathering: Gathering, gathered: Gathered): Way {
    const starts = gathered.takes ? lifted(set, gathered.lies, 1) : lying(gathered.lies);
    const leads = { ...lifted(set, takerOf(gathering.cards).lies, 1), turn: starts.turn };
    const lands = onPile(gathering, gathered, starts.turn);
    return (at) => {
        const along = phase(at, set.gatherSeconds, set.glideSeconds);
        return {
            ...between(starts, between(leads, lands, smooth(along)), 1 - (1 - along) ** 3),
            shown: 1 - piled(set, at),
        };
    };
}

/**
 * A finished trick is gathered onto its taker's pile, from its first move. A set that springs pushes the cards to an
 * untidy heap, the taking card last on top, squares the heap, turns it over and throws it onto the pile, where it lands
 * short and slides out. Any other set lets the taking card go straight to the pile and collect the others on its way,
 * face up. A name stays where its card lay and fades there.
 */
export function gatherTimeline(set: GatherSet, seed: string, gathering: Gathering): Timeline<GatherTracks> {
    const tracksOf = (gathered: Gathered): CardTracks => {
        const way = set.springs ? sprungWay(set, seed, gathering, gathered) : openWay(set, gathering, gathered);
        return {
            card: (at) => drawnFrom(gathered.lies, way(at)).card,
            shade: (at) => drawnFrom(gathered.lies, way(at)).shade,
            rear: (at) => Number(way(at).facing <= 0),
            rim: (at) => (set.springs ? 1 - phase(at, set.gatherSeconds, RIM_FADES_SECONDS) : 1),
            name: (at) => 1 - phase(at, 0, NAME_FADES_SECONDS),
        };
    };
    const instants = gatherInstants(set);
    return {
        seconds: instants.piled - instants.gathers,
        tracks: { cards: gathering.cards.map(tracksOf), pile: (at) => piled(set, at) },
    };
}

/**
 * The taker's chair as the trick reaches its pile, from the trick's first move: its gold ring flashes, and in a set
 * that springs the chair hops.
 */
export function takerTimeline(set: GatherSet): Timeline<TakerTracks> {
    const touches = touchesAfter(set);
    const fades = set.springs ? FLASH_FADES_SECONDS.springs : FLASH_FADES_SECONDS.glides;
    const hopped = (seconds: number): number => phase(seconds, touches, HOP_SECONDS);
    return {
        seconds: touches + FLASH_STANDS_SECONDS + fades,
        tracks: {
            flash: (seconds) =>
                phase(seconds, touches, FLASH_RISES_SECONDS) *
                (1 - phase(seconds, touches + FLASH_STANDS_SECONDS, fades)),
            hop: set.springs
                ? (seconds) => ({
                      x: 0,
                      y: -HOP_PIXELS * 4 * hopped(seconds) * (1 - hopped(seconds)),
                      turn: 0,
                      wide: 1,
                      tall: 1,
                      opacity: 1,
                  })
                : null,
        },
    };
}
