import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Cue } from "#lib/cues.ts";
import { MOTION_SETS } from "#lib/motionSets.ts";
import type { LastTrick, Playing, Table } from "../routes/(start)/tables.ts";

vi.mock("./tableSound.ts", () => ({ soundForGlide: vi.fn() }));

const KEY = "skat.settings";
const TAKER_SEAT = 3;
const LOOKED_AT_SEAT = 2;
const TRICK: LastTrick = {
    cards: [
        { suit: "kreuz", rank: "king" },
        { suit: "herz", rank: "nine" },
        { suit: "kreuz", rank: "ace" },
    ],
    leader_seat: 1,
    taker_seat: TAKER_SEAT,
};
const TAKEN: Cue = { kind: "trick-taken", trick: TRICK };
const CARD_PLAYED: Cue = { kind: "card-played", seat: TAKER_SEAT, card: { suit: "kreuz", rank: "ace" } };
const AUCTION_ENDED: Cue = { kind: "auction-ended" };
const PLAYING = { turn_seat: TAKER_SEAT } as Playing;
const TABLE_IN_PLAY = { hand: { playing: PLAYING } } as unknown as Table;
const TABLE_BETWEEN_HANDS = { hand: null } as unknown as Table;
const REST_MILLISECONDS = MOTION_SETS.verspielt.trickRestSeconds * 1000;
const GLIDE_MILLISECONDS = (MOTION_SETS.verspielt.trickGatherSeconds + MOTION_SETS.verspielt.trickGlideSeconds) * 1000;

// The stage is module state, so each test reads a module of its own, on a page whose player stored `stored`.
async function stageOnAPage(stored: Record<string, unknown>, options: { hidden?: boolean } = {}) {
    vi.resetModules();
    vi.stubGlobal("window", {
        localStorage: { getItem: (key: string) => (key === KEY ? JSON.stringify(stored) : null) },
    });
    vi.stubGlobal("document", { hidden: options.hidden === true });
    const { loadSettings } = await import("#lib/settings.svelte.ts");
    loadSettings();
    const { soundForGlide } = await import("./tableSound.ts");
    const stage = await import("#lib/stage.svelte.ts");
    return { stage, sweeps: vi.mocked(soundForGlide) };
}

// A device that asks for reduced motion moves the table only when the player overrides it.
const MOVING = { replayMotion: true };

beforeEach(() => {
    vi.useFakeTimers();
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe("a finished trick on the page's stage", () => {
    it("rests, then glides to its taker's pile with the sweep sound, then settles", async () => {
        const { stage, sweeps } = await stageOnAPage(MOVING);

        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED, TAKEN]);

        expect(stage.trickIsMoving()).toBe(true);
        expect(stage.currentStage().trick).toEqual(TRICK);
        expect(stage.currentStage().before).toBe(PLAYING);
        expect(stage.sweepingTo()).toBeNull();
        expect(sweeps).not.toHaveBeenCalled();

        vi.advanceTimersByTime(REST_MILLISECONDS);

        expect(stage.sweepingTo()).toBe(TAKER_SEAT);
        expect(sweeps).toHaveBeenCalledTimes(1);

        vi.advanceTimersByTime(GLIDE_MILLISECONDS);

        expect(stage.trickIsMoving()).toBe(false);
        expect(stage.sweepingTo()).toBeNull();
        expect(sweeps).toHaveBeenCalledTimes(1);
    });

    it("shows at once and still sounds the sweep when the device asks for reduced motion", async () => {
        const { stage, sweeps } = await stageOnAPage({});

        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED, TAKEN]);

        expect(stage.trickIsMoving()).toBe(false);
        expect(sweeps).toHaveBeenCalledTimes(1);
    });

    it("shows at once and still sounds the sweep while the window is hidden", async () => {
        const { stage, sweeps } = await stageOnAPage(MOVING, { hidden: true });

        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED, TAKEN]);

        expect(stage.trickIsMoving()).toBe(false);
        expect(sweeps).toHaveBeenCalledTimes(1);
    });

    it("keeps no playing before it when the table before was between hands", async () => {
        const { stage } = await stageOnAPage(MOVING);

        stage.receiveOnStage(TABLE_BETWEEN_HANDS, [CARD_PLAYED, TAKEN]);

        expect(stage.currentStage().before).toBeNull();
    });

    it("lies on the felt with no stage under „liegen lassen“ when no lead follows", async () => {
        const { stage, sweeps } = await stageOnAPage({ ...MOVING, lastTrick: "stay" });

        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED, TAKEN]);

        expect(stage.trickIsMoving()).toBe(false);
        expect(sweeps).not.toHaveBeenCalled();
    });

    it("settles at once when the window jumps, sounds the sweep it had not yet heard and ends the wait", async () => {
        const { stage, sweeps } = await stageOnAPage(MOVING);
        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED, TAKEN]);

        stage.jumpStage();
        vi.advanceTimersByTime(REST_MILLISECONDS + GLIDE_MILLISECONDS);

        expect(stage.trickIsMoving()).toBe(false);
        expect(sweeps).toHaveBeenCalledTimes(1);
    });

    it("settles at once with the first table of a page and ends the wait", async () => {
        const { stage, sweeps } = await stageOnAPage(MOVING);
        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED, TAKEN]);

        stage.receiveOnStage(undefined, []);
        vi.advanceTimersByTime(REST_MILLISECONDS + GLIDE_MILLISECONDS);

        expect(stage.trickIsMoving()).toBe(false);
        expect(sweeps).not.toHaveBeenCalled();
    });

    it("settles at once when the page resets, so a table left behind sounds nothing", async () => {
        const { stage, sweeps } = await stageOnAPage(MOVING);
        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED, TAKEN]);

        stage.resetStage();
        vi.advanceTimersByTime(REST_MILLISECONDS + GLIDE_MILLISECONDS);

        expect(stage.trickIsMoving()).toBe(false);
        expect(sweeps).not.toHaveBeenCalled();
    });
});

describe("the look at a pile's last trick", () => {
    it("holds the seat looked at until the player stops", async () => {
        const { stage } = await stageOnAPage(MOVING);

        expect(stage.lookingAt()).toBeNull();
        stage.lookAtLastTrick(LOOKED_AT_SEAT);
        expect(stage.lookingAt()).toBe(LOOKED_AT_SEAT);
        stage.stopLooking();

        expect(stage.lookingAt()).toBeNull();
    });

    it("ends with the next card laid and with the first table of a page, not with other news", async () => {
        const { stage } = await stageOnAPage(MOVING);
        stage.lookAtLastTrick(LOOKED_AT_SEAT);

        stage.receiveOnStage(TABLE_IN_PLAY, [AUCTION_ENDED]);
        expect(stage.lookingAt()).toBe(LOOKED_AT_SEAT);
        stage.receiveOnStage(TABLE_IN_PLAY, [CARD_PLAYED]);
        expect(stage.lookingAt()).toBeNull();

        stage.lookAtLastTrick(LOOKED_AT_SEAT);
        stage.receiveOnStage(undefined, []);
        expect(stage.lookingAt()).toBeNull();
    });
});
