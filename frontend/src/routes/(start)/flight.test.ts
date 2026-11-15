import { describe, expect, it } from "vitest";
import { OTHER_SEAT, OWN_SEAT, THIRD_SEAT, tableSeenFrom } from "#lib/tableSound.fixtures.ts";
import { flightOf } from "./flight.ts";
import type { Reaction, Thrown } from "./reaction.ts";

const { chairs } = tableSeenFrom(OWN_SEAT);
const WATCHER = null;
const SEATS = [OWN_SEAT, OTHER_SEAT, THIRD_SEAT];

const thrown = (by_seat: number | null, reaction: Reaction, number = 1): Thrown => ({
    number,
    reaction,
    by_seat,
    by_name: by_seat === null ? null : `player ${String(by_seat)}`,
});

describe("where a reaction thrown at the table flies", () => {
    it("starts an emote at the chair of its thrower and ends it on the felt with a trail", () => {
        const flights = SEATS.map((seat) => flightOf(thrown(seat, "fire"), chairs));

        expect(new Set(flights.map((flight) => `${String(flight.origin.x)} ${String(flight.origin.y)}`)).size).toBe(
            SEATS.length,
        );
        for (const flight of flights) {
            expect(flight.knocked).toBe(false);
            expect(flight.trail?.split("L")).toHaveLength(8);
            expect(flight.origin).not.toEqual(flight.landing);
        }
    });

    it("starts a watcher's emote where no chair's emote starts", () => {
        const chairOrigins = SEATS.map((seat) => flightOf(thrown(seat, "fire"), chairs).origin);

        expect(chairOrigins).not.toContainEqual(flightOf(thrown(WATCHER, "fire"), chairs).origin);
    });

    it("lands emotes thrown together on different places of the felt", () => {
        const landings = [1, 2, 3].map((number) => flightOf(thrown(OWN_SEAT, "fire", number), chairs).landing);

        expect(new Set(landings.map((landing) => JSON.stringify(landing))).size).toBe(landings.length);
    });

    it("lands a knock where it starts, with no trail", () => {
        const flights = SEATS.map((seat) => flightOf(thrown(seat, "knock"), chairs));

        for (const flight of flights) {
            expect(flight.knocked).toBe(true);
            expect(flight.trail).toBeNull();
            expect(flight.origin).toEqual(flight.landing);
        }
    });

    it("lands a watcher's knock where no chair's knock lands", () => {
        const chairLandings = SEATS.map((seat) => flightOf(thrown(seat, "knock"), chairs).landing);

        expect(chairLandings).not.toContainEqual(flightOf(thrown(WATCHER, "knock"), chairs).landing);
    });
});
