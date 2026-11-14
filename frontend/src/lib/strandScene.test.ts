import { describe, expect, it } from "vitest";
import { beachOf, BEACH_VIEWS, type BeachSize } from "./strandScene.ts";

const SIZES: BeachSize[] = ["phone", "desktop"];

describe("the beach behind a Strandbar table", () => {
    it.each(SIZES)("is drawn the same on every load of the %s frame", (size) => {
        expect(beachOf(size)).toEqual(beachOf(size));
    });

    it.each(SIZES)("keeps the sky above the sea and the sea above the sand in the %s frame", (size) => {
        const beach = beachOf(size);

        expect(0 < beach.horizon && beach.horizon < beach.shore && beach.shore < BEACH_VIEWS[size].height).toBe(true);
    });

    it.each(SIZES)("lays its stars in the sky and its sand grains on the sand in the %s frame", (size) => {
        const beach = beachOf(size);

        expect(beach.stars.every((star) => star.y <= beach.horizon)).toBe(true);
        expect(beach.speckle.every((grain) => grain.y >= beach.shore)).toBe(true);
    });

    it("hangs the string of lights over the desktop's sky only", () => {
        expect([beachOf("phone").bulbs.length, beachOf("desktop").bulbs.length > 0]).toEqual([0, true]);
    });
});
