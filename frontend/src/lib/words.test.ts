// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { listFormat, pageLanguage, words } from "#lib/words.ts";
import { sourceLanguage } from "#lib/words/index.ts";

describe("the language of the page", () => {
    it.each(["de", "fr"])("is the tag %s of <html lang> when the app offers it", (tag) => {
        expect(pageLanguage(tag, ["de", "fr"])).toBe(tag);
    });

    it.each(["", "xx", "DE", "de-AT"])("is the source language for the tag '%s' the app does not offer", (tag) => {
        expect(pageLanguage(tag, ["de", "fr"])).toBe(sourceLanguage);
    });

    it.each(["de", ""])("is read from the document of the browser when its lang says '%s'", async (tag) => {
        document.documentElement.lang = tag;
        vi.resetModules();

        const loaded = await import("#lib/words.ts");

        expect(loaded.language).toBe(sourceLanguage);
        expect(loaded.words["app.name"]).toBe(words["app.name"]);
    });
});

describe("the list of names", () => {
    it.each([
        { names: ["Anna"], listed: "Anna" },
        { names: ["Anna", "Ben"], listed: "Anna und Ben" },
        { names: ["Anna", "Ben", "Carla"], listed: "Anna, Ben und Carla" },
    ])("reads $listed for $names.length name(s)", ({ names, listed }) => {
        expect(listFormat.format(names)).toBe(listed);
    });
});
