import { afterEach, describe, expect, it, vi } from "vitest";
import { words } from "#lib/words.ts";
import {
    announcedWord,
    cardName,
    copyTableLink,
    drawingOrder,
    gameLabel,
    gameWord,
    isSuitGame,
    positionWord,
    tablePath,
    type Chair,
    type Game,
    type Position,
} from "./tables.ts";

const TABLE_ID = "a".repeat(32);

describe("the table's seats and link", () => {
    const chair = (seat: number, isMine = false): Chair => ({
        seat,
        occupant_name: null,
        occupant_kind: null,
        is_mine: isMine,
        is_away: false,
        ready: false,
        total: null,
        hand: null,
        former_holder_name: null,
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("draws the viewer's own chair last", () => {
        expect(drawingOrder([chair(0), chair(1, true), chair(2)]).map((each) => each.seat)).toEqual([2, 0, 1]);
    });

    it("keeps the order when no chair is the viewer's", () => {
        expect(drawingOrder([chair(0), chair(1)]).map((each) => each.seat)).toEqual([0, 1]);
    });

    it.each([
        ["forehand", words["game.forehand"]],
        ["middlehand", words["game.middlehand"]],
        ["rearhand", words["game.rearhand"]],
    ] as [Position, string][])("names the position %s with its word", (position, word) => {
        expect(positionWord(position)).toBe(word);
    });

    it.each([
        ["karo", words["game.karo"]],
        ["herz", words["game.herz"]],
        ["pik", words["game.pik"]],
        ["kreuz", words["game.kreuz"]],
        ["grand", words["game.grand"]],
        ["null", words["game.null"]],
    ] as [Game, string][])("names the game %s with its word", (game, word) => {
        expect(gameWord(game)).toBe(word);
    });

    it.each([
        ["a plain game", "grand", false, false, "none", words["game.grand"], null],
        ["a Hand game", "grand", true, false, "none", words["game.handName"]({ game: words["game.grand"] }), null],
        [
            "an ouvert game, which includes Hand",
            "grand",
            true,
            true,
            "schwarz",
            words["game.ouvertName"]({ game: words["game.grand"] }),
            null,
        ],
        [
            "Null ouvert after the take",
            "null",
            false,
            true,
            "none",
            words["game.ouvertName"]({ game: words["game.null"] }),
            null,
        ],
        [
            "Null ouvert Hand",
            "null",
            true,
            true,
            "none",
            words["game.ouvertHandName"]({ game: words["game.null"] }),
            null,
        ],
        [
            "a Hand game with Schneider announced",
            "herz",
            true,
            false,
            "schneider",
            words["game.handName"]({ game: words["game.herz"] }),
            words["game.announcedSchneider"],
        ],
        [
            "a Hand game with Schwarz announced",
            "grand",
            true,
            false,
            "schwarz",
            words["game.handName"]({ game: words["game.grand"] }),
            words["game.announcedSchwarz"],
        ],
    ] as const)("labels %s", (_name, game, hand, ouvert, announcement, name, announced) => {
        expect(gameLabel({ game, hand, ouvert, announcement })).toEqual({ name, announcement: announced });
    });

    it.each([
        ["none", null],
        ["schneider", words["game.announcedSchneider"]],
        ["schwarz", words["game.announcedSchwarz"]],
    ] as const)("words the announcement %s", (announcement, word) => {
        expect(announcedWord(announcement)).toBe(word);
    });

    it.each([
        ["karo", true],
        ["herz", true],
        ["pik", true],
        ["kreuz", true],
        ["grand", false],
        ["null", false],
    ] as [Game, boolean][])("tells whether the game %s is a suit game", (game, suited) => {
        expect(isSuitGame(game)).toBe(suited);
    });

    it("names a card by its suit's game word and its rank word", () => {
        expect(cardName({ suit: "herz", rank: "ace" })).toBe(
            words["game.cardName"]({ suit: words["game.herz"], rank: words["game.rankAce"] }),
        );
    });

    it("copies the table's link to the clipboard", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        vi.stubGlobal("navigator", { clipboard: { writeText } });
        vi.stubGlobal("location", { origin: "https://skat.test" });

        expect(await copyTableLink(TABLE_ID)).toBe(true);
        expect(writeText).toHaveBeenCalledWith(`https://skat.test${tablePath(TABLE_ID)}`);
    });

    it("reports a refused clipboard as not copied", async () => {
        vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
        vi.stubGlobal("location", { origin: "https://skat.test" });

        expect(await copyTableLink(TABLE_ID)).toBe(false);
    });
});
