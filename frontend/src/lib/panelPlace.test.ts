import { describe, expect, it, vi } from "vitest";
import { applyPanelPlace, EDGE_MARGIN, placePanel, type Box, type PanelPlace } from "./panelPlace.ts";

const PHONE = { width: 390, height: 800 };
const WANTED = 328;
const ROUND_BUTTON = 40;

function buttonAt(left: number, top: number): Box {
    return { left, top, width: ROUND_BUTTON, height: ROUND_BUTTON };
}

const middleOf = (box: Box): number => box.left + box.width / 2;

describe("placePanel", () => {
    it.each([
        { name: "near the left edge", button: buttonAt(8, 10) },
        { name: "in the middle", button: buttonAt(175, 10) },
        { name: "near the right edge", button: buttonAt(342, 10) },
    ])("keeps the panel inside the edge margin $name", ({ button }) => {
        const place = placePanel(button, PHONE, WANTED, "below");

        expect(place.left).toBeGreaterThanOrEqual(EDGE_MARGIN);
        expect(place.left + place.width).toBeLessThanOrEqual(PHONE.width - EDGE_MARGIN);
    });

    it("puts the caret over the middle of the button when the panel can centre on it", () => {
        const button = buttonAt(175, 10);

        const place = placePanel(button, PHONE, WANTED, "below");

        expect(place.left + place.caret).toBe(middleOf(button));
    });

    it.each([
        { name: "left", button: buttonAt(8, 10) },
        { name: "right", button: buttonAt(342, 10) },
    ])("keeps the caret over the $name button when the panel is pushed off its middle", ({ button }) => {
        const place = placePanel(button, PHONE, WANTED, "below");

        const caretAt = place.left + place.caret;
        expect(caretAt).toBeGreaterThanOrEqual(button.left);
        expect(caretAt).toBeLessThanOrEqual(button.left + button.width);
    });

    it("shrinks the panel in a viewport narrower than the wanted width", () => {
        const place = placePanel(buttonAt(10, 10), { width: 320, height: 600 }, WANTED, "below");

        expect(place.width).toBe(320 - 2 * EDGE_MARGIN);
        expect(place.left).toBe(EDGE_MARGIN);
    });

    it("hangs the panel below the button and leaves the room down to the edge margin", () => {
        const button = buttonAt(175, 10);

        const place = placePanel(button, PHONE, WANTED, "below");

        expect(place.edge).toBeGreaterThan(button.top + button.height);
        expect(place.edge + place.room).toBeLessThanOrEqual(PHONE.height - EDGE_MARGIN);
    });

    it("hangs the panel above the button, its edge counted from the bottom, and leaves the room up to the edge margin", () => {
        const button = buttonAt(175, 700);

        const place = placePanel(button, PHONE, WANTED, "above");

        expect(place.edge).toBeGreaterThan(PHONE.height - button.top);
        expect(PHONE.height - place.edge - place.room).toBeGreaterThanOrEqual(EDGE_MARGIN);
    });

    it("lets a panel take at most seven tenths of a tall viewport", () => {
        const place = placePanel(buttonAt(175, 10), { width: 390, height: 1000 }, WANTED, "below");

        expect(place.room).toBe(700);
    });

    it("takes the room that is left over a short viewport", () => {
        const place = placePanel(buttonAt(175, 300), { width: 390, height: 600 }, WANTED, "below");

        expect(place.room).toBeLessThan(0.7 * 600);
    });

    it("never offers a negative room", () => {
        const place = placePanel(buttonAt(175, 590), { width: 390, height: 600 }, WANTED, "below");

        expect(place.room).toBe(0);
    });
});

describe("applyPanelPlace", () => {
    it("sets the place as custom properties and nothing else", () => {
        const setProperty = vi.fn();
        const place: PanelPlace = { width: 328, left: 31, caret: 100, edge: 62, room: 500 };

        applyPanelPlace({ style: { setProperty } }, place);

        expect(Object.fromEntries(setProperty.mock.calls as [string, string][])).toEqual({
            "--panel-width": "328px",
            "--panel-left": "31px",
            "--panel-caret": "100px",
            "--panel-edge": "62px",
            "--panel-room": "500px",
        });
    });
});
