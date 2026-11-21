import { describe, expect, it } from "vitest";
import { MOTION_SETS } from "#lib/motionSets.ts";
import {
    gatherInstants,
    gatherTimeline,
    liftTimeline,
    takerTimeline,
    type Gathered,
    type Gathering,
} from "#lib/takt/gather.ts";
import { sampled, type Place, type Pose, type Track } from "#lib/takt/timeline.ts";
import { RANK_TOKENS, SUIT_TOKENS } from "#lib/wire.ts";
import type { Card } from "../../routes/(start)/tables.ts";

const SEED = "table/1/8";
const NEXT_GAME = "table/1/9";
const SETS = Object.values(MOTION_SETS).map((set) => ({ id: set.id, trick: set.trick }));
const SPRINGING = MOTION_SETS.verspielt.trick;
const OPEN = MOTION_SETS.dezent.trick;
const FRAME_SECONDS = 1 / 60;
const WIDTH = 70;
const [FIRST, SECOND, TAKING] = RANK_TOKENS.slice(0, 3).map((rank): Card => ({ suit: SUIT_TOKENS[0], rank })) as [
    Card,
    Card,
    Card,
];
// The slots of a felt, unturned, so a pose reads in the page's own directions.
const LEFT: Place = { x: 110, y: 400, width: WIDTH, turn: 0 };
const RIGHT: Place = { x: 280, y: 400, width: WIDTH, turn: 0 };
const NEAR: Place = { x: 195, y: 440, width: WIDTH, turn: 0 };
const MIDDLE = { x: 195, y: 410 };
// A pile's top card: smaller than a laid card, and crossed against the one below it.
const PILE: Place = { x: 330, y: 200, width: 40, turn: 87 };

// A trick whose third card took it, each card in the slot one seat sees it in.
function trickSeenIn(slots: readonly [Place, Place, Place]): Gathering {
    const cards: Gathered[] = [FIRST, SECOND, TAKING].map((card, played) => ({
        card,
        lies: slots[played] as Place,
        takes: card === TAKING,
    }));
    return { cards, middle: MIDDLE, pile: PILE };
}

const SEEN = trickSeenIn([LEFT, RIGHT, NEAR]);
const SEEN_FROM_THE_NEXT_SEAT = trickSeenIn([NEAR, LEFT, RIGHT]);
const TAKER = 2;

// Where a pose draws the middle of a part that rests unturned at `lies`, and how it is turned on the page.
const drawnAt = (lies: Place, pose: Pose) => ({ x: lies.x + pose.x, y: lies.y + pose.y, turn: pose.turn });
const offTheMiddle = (lies: Place, pose: Pose): number =>
    Math.hypot(drawnAt(lies, pose).x - MIDDLE.x, drawnAt(lies, pose).y - MIDDLE.y) / WIDTH;
const instantsOf = (seconds: number): number[] => sampled((at) => at, seconds, FRAME_SECONDS);

describe.each(SETS)("a finished trick in the set $id", ({ trick }) => {
    it("lifts its taking card while it rests, is gathered when the rest is over, and is piled last", () => {
        const { lifts, gathers, glides, piled } = gatherInstants(trick);

        expect(lifts).toBeGreaterThan(0);
        expect(lifts).toBeLessThan(gathers);
        expect(gathers).toBeLessThanOrEqual(glides);
        expect(glides).toBeLessThan(piled);
    });
});

describe.each(SETS)("the lift of the card that took a trick in the set $id", ({ trick }) => {
    const { tracks, seconds } = liftTimeline(trick, NEAR);

    it("starts where the card lies, on its shade and with no rim", () => {
        expect(tracks.card(0)).toEqual({ x: 0, y: 0, turn: 0, wide: 1, tall: 1, opacity: 1 });
        expect(tracks.shade(0)).toEqual(tracks.card(0));
        expect(tracks.rim(0)).toBe(0);
    });

    it("raises the card by the set's rise above its shade, which falls away below it, and shows the whole rim", () => {
        const [card, shade] = [tracks.card(seconds), tracks.shade(seconds)];

        expect(card.y).toBeLessThan(0);
        expect(shade.y).toBeGreaterThan(0);
        expect((shade.y - card.y) / WIDTH).toBeCloseTo(trick.rise, 2);
        expect(card.x).toBeCloseTo(0);
        expect(tracks.rim(seconds)).toBe(1);
    });

    it("presses a seal on once the rim shows: hidden and larger at first, whole and its own size at the end", () => {
        const shown = instantsOf(seconds).filter((at) => tracks.seal(at).opacity > 0);

        expect(tracks.seal(0).opacity).toBe(0);
        expect(tracks.rim(shown[0] as number)).toBeGreaterThan(0);
        expect(tracks.seal(shown[0] as number).wide).toBeGreaterThan(1);
        expect(tracks.seal(seconds)).toMatchObject({ x: 0, y: 0, turn: 0, opacity: 1 });
        expect(tracks.seal(seconds).wide).toBeCloseTo(1, 2);
        expect(tracks.seal(seconds).tall).toBe(tracks.seal(seconds).wide);
    });
});

describe("the lift in a set that springs", () => {
    const { tracks, seconds } = liftTimeline(SPRINGING, NEAR);

    it("swings the card past the height it comes to stand at, and makes it larger", () => {
        const heights = instantsOf(seconds).map((at) => -tracks.card(at).y);

        expect(Math.max(...heights)).toBeGreaterThan(-tracks.card(seconds).y * 1.05);
        expect(tracks.card(seconds).tall).toBeGreaterThan(1);
    });

    it("lets the seal give way as it hits", () => {
        expect(Math.min(...instantsOf(seconds).map((at) => tracks.seal(at).wide))).toBeLessThan(1);
    });
});

describe("the lift in a set that does not spring", () => {
    const { tracks, seconds } = liftTimeline(OPEN, NEAR);

    it("raises the card without passing its height, as large as it lies, and presses the seal on without a rebound", () => {
        const heights = instantsOf(seconds).map((at) => -tracks.card(at).y);

        for (const [index, height] of heights.slice(1).entries())
            expect(height).toBeGreaterThanOrEqual(heights[index] as number);
        expect(tracks.card(seconds).tall).toBe(1);
        expect(Math.min(...instantsOf(seconds).map((at) => tracks.seal(at).wide))).toBe(1);
    });
});

describe.each(SETS)("the gathering of a trick in the set $id", ({ trick }) => {
    const { tracks, seconds } = gatherTimeline(trick, SEED, SEEN);
    const lifted = liftTimeline(trick, NEAR);

    it("starts with each card where it lies and the taking card as its lift left it", () => {
        for (const [played, { card, shade }] of tracks.cards.entries()) {
            if (played === TAKER) continue;
            expect(card(0)).toEqual({ x: 0, y: 0, turn: 0, wide: 1, tall: 1, opacity: 1 });
            expect(shade(0)).toEqual(card(0));
        }
        const [taking, left] = [tracks.cards[TAKER]?.card(0) as Pose, lifted.tracks.card(lifted.seconds)];
        expect(taking.y).toBeCloseTo(left.y, 0);
        expect(taking.tall).toBeCloseTo(left.tall, 2);
    });

    it("ends with every card on the pile's top card, as small and as turned as it", () => {
        const justBefore = seconds - 0.001;

        for (const [played, { card }] of tracks.cards.entries()) {
            const lies = SEEN.cards[played]?.lies as Place;
            const arrived = card(justBefore);
            expect(drawnAt(lies, arrived).x).toBeCloseTo(PILE.x, 0);
            expect(drawnAt(lies, arrived).y).toBeCloseTo(PILE.y, 0);
            expect(arrived.turn).toBeCloseTo(PILE.turn, 0);
            expect(arrived.tall).toBeCloseTo(PILE.width / WIDTH, 2);
            expect(arrived.wide).toBeCloseTo(PILE.width / WIDTH, 2);
        }
    });

    it("becomes the pile's top card: that card shows as much as the trick no longer does", () => {
        expect(tracks.pile(0)).toBe(0);
        expect(tracks.pile(seconds)).toBe(1);
        for (const at of instantsOf(seconds))
            for (const { card, shade } of tracks.cards) {
                expect(card(at).opacity + tracks.pile(at)).toBeCloseTo(1);
                expect(shade(at).opacity).toBeLessThanOrEqual(card(at).opacity);
            }
    });

    it("lets each name fade where its card lay, before the cards are on their way", () => {
        for (const { name } of tracks.cards) {
            expect(name(0)).toBe(1);
            expect(name(seconds / 2)).toBe(0);
        }
    });

    it("turns a card the shorter way onto a pile that lies turned the other way round", () => {
        const turnedBack = gatherTimeline(trick, SEED, { ...SEEN, pile: { ...PILE, turn: PILE.turn - 360 } });

        expect(turnedBack.tracks.cards[0]?.card(seconds - 0.001).turn).toBeCloseTo(PILE.turn, 0);
    });
});

describe("the gathering in a set that springs", () => {
    const { tracks, seconds } = gatherTimeline(SPRINGING, SEED, SEEN);
    const heapedAt = SPRINGING.gatherSeconds;
    const heapOf = (gathering: Gathering, seed = SEED) =>
        gatherTimeline(SPRINGING, seed, gathering).tracks.cards.map(({ card }, played) =>
            drawnAt(gathering.cards[played]?.lies as Place, card(heapedAt)),
        );

    it("sets the cards out one after another, the taking card last", () => {
        const moved = tracks.cards.map(({ card }) => JSON.stringify(card(0.001)) !== JSON.stringify(card(0)));

        expect(moved).toEqual([true, false, false]);
    });

    it("pushes the cards to an untidy heap in the middle, face up and on the felt", () => {
        for (const [played, { card, shade, rear }] of tracks.cards.entries()) {
            const lies = SEEN.cards[played]?.lies as Place;
            expect(offTheMiddle(lies, card(heapedAt))).toBeLessThan(0.2);
            expect(card(heapedAt).y).toBeCloseTo(shade(heapedAt).y, 0);
            expect(rear(heapedAt)).toBe(0);
        }
        const turns = heapOf(SEEN).map(({ turn }) => Math.round(turn));
        expect(new Set(turns).size).toBe(turns.length);
    });

    it("heaps each card the same way from whichever seat the trick is seen", () => {
        const [here, there] = [heapOf(SEEN), heapOf(SEEN_FROM_THE_NEXT_SEAT)];

        for (const [played, card] of here.entries()) {
            const other = there[played] as (typeof there)[number];
            expect(Math.abs(card.x - other.x) / WIDTH).toBeLessThan(0.05);
            expect(Math.abs(card.y - other.y) / WIDTH).toBeLessThan(0.05);
            expect(Math.abs(card.turn - other.turn)).toBeLessThan(2);
        }
    });

    it("heaps the cards the same way whenever it is asked, and another way in the next game", () => {
        expect(heapOf(trickSeenIn([LEFT, RIGHT, NEAR]))).toEqual(heapOf(SEEN));
        expect(heapOf(SEEN, NEXT_GAME)).not.toEqual(heapOf(SEEN));
    });

    it("turns the heap over above the felt: edge-on as the backs come up, and face down from then on", () => {
        for (const { card, shade, rear } of tracks.cards) {
            const backs = instantsOf(seconds).filter((at) => rear(at) === 1);
            const turned = backs[0] as number;
            expect(turned).toBeGreaterThan(heapedAt);
            expect(card(turned).wide).toBeLessThan(card(turned).tall * 0.3);
            expect(card(turned).y).toBeLessThan(shade(turned).y);
            expect(backs).toEqual(instantsOf(seconds).filter((at) => at >= turned));
        }
    });

    it("has squared the heap when it stands on edge, so no two cards cross there", () => {
        const { card: first } = tracks.cards[0] as (typeof tracks.cards)[number];
        const onEdge = sampled((at) => at, seconds, 0.001).reduce((thinnest, at) =>
            first(at).wide < first(thinnest).wide ? at : thinnest,
        );
        const turns = tracks.cards.map(({ card }) => card(onEdge).turn);

        expect(Math.max(...turns) - Math.min(...turns)).toBeLessThan(1);
    });

    it("throws the turned heap through the air and has it lie on its shade at the pile", () => {
        const { card, shade, rear } = tracks.cards[TAKER] as (typeof tracks.cards)[number];
        const thrown = instantsOf(seconds).filter((at) => rear(at) === 1 && card(at).y < shade(at).y - 1);
        const midway = thrown[Math.floor(thrown.length / 2)] as number;

        expect(Math.abs(drawnAt(NEAR, card(midway)).x - MIDDLE.x)).toBeGreaterThan(WIDTH / 2);
        expect(card(seconds - 0.001).y).toBeCloseTo(shade(seconds - 0.001).y, 0);
    });

    it("lets the brass rim go as the heap turns over", () => {
        const rim = tracks.cards[TAKER]?.rim as (at: number) => number;

        expect(rim(heapedAt)).toBe(1);
        expect(rim(seconds)).toBe(0);
    });
});

describe("the gathering in a set that does not spring", () => {
    const { tracks, seconds } = gatherTimeline(OPEN, SEED, SEEN);

    it("glides the trick open: no back shows, and the brass rim stays on the taking card", () => {
        for (const at of instantsOf(seconds))
            for (const { rear, rim } of tracks.cards) {
                expect(rear(at)).toBe(0);
                expect(rim(at)).toBe(1);
            }
    });

    it("lets the other cards join the taking card on its way to the pile", () => {
        const apartAt = (at: number, played: number): number => {
            const [card, taking] = [tracks.cards[played]?.card(at) as Pose, tracks.cards[TAKER]?.card(at) as Pose];
            const lies = SEEN.cards[played]?.lies as Place;
            return Math.hypot(
                drawnAt(lies, card).x - drawnAt(NEAR, taking).x,
                drawnAt(lies, card).y - drawnAt(NEAR, taking).y,
            );
        };

        for (const played of [0, 1]) expect(apartAt(seconds / 2, played)).toBeLessThan(apartAt(0, played) / 2);
    });

    it("draws the trick alike in the next game, since nothing of it is drawn by lot", () => {
        const next = gatherTimeline(OPEN, NEXT_GAME, SEEN);

        expect(next.tracks.cards[0]?.card(seconds / 2)).toEqual(tracks.cards[0]?.card(seconds / 2));
    });
});

describe.each(SETS)("the chair that takes a trick in the set $id", ({ trick }) => {
    const { tracks, seconds } = takerTimeline(trick);
    const instants = instantsOf(seconds);

    it("flashes its ring once, no sooner than the trick is on its way and no later than it is piled", () => {
        const flashing = instants.filter((at) => tracks.flash(at) > 0);
        const { gathers, glides, piled } = gatherInstants(trick);

        expect(flashing[0]).toBeGreaterThan(glides - gathers);
        expect(flashing[0]).toBeLessThanOrEqual(piled - gathers + FRAME_SECONDS);
        expect(Math.max(...instants.map(tracks.flash))).toBeCloseTo(1);
        expect(tracks.flash(seconds)).toBeCloseTo(0);
    });
});

describe("the chair that takes a trick", () => {
    const { tracks, seconds } = takerTimeline(SPRINGING);
    const hop = tracks.hop as Track<Pose>;

    it("hops as the trick lands in a set that springs", () => {
        expect(Math.min(...instantsOf(seconds).map((at) => hop(at).y))).toBeLessThan(-1);
    });

    it("stands where it stood before the trick arrives and when the flash is over", () => {
        for (const at of [0, seconds]) {
            expect(hop(at).y).toBeCloseTo(0);
            expect(hop(at)).toMatchObject({ x: 0, turn: 0, wide: 1, tall: 1, opacity: 1 });
        }
    });

    it("has no hop in a set that does not spring", () => {
        expect(takerTimeline(OPEN).tracks.hop).toBeNull();
    });
});
