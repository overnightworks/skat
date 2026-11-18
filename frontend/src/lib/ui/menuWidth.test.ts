import { describe, expect, it } from "vitest";
import { menuPanelWidth } from "#lib/ui/menuWidth.ts";

describe("the table menu's width", () => {
    const phoneWidth = 390;
    const desktopWidth = 1280;

    it("fits inside a phone's viewport", () => {
        expect(menuPanelWidth(phoneWidth)).toBeLessThan(phoneWidth);
    });

    it("widens on a desktop viewport", () => {
        expect(menuPanelWidth(desktopWidth)).toBeGreaterThan(menuPanelWidth(phoneWidth));
    });
});
