// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { listFormat, pageLanguage } from "#lib/words.ts";
import { sourceLanguage } from "#lib/words/index.ts";

describe("the language of the page", () => {
    it.each(["de", "fr"])("is the tag %s of <html lang> when the app offers it", (tag) => {
        expect(pageLanguage(tag, ["de", "fr"])).toBe(tag);
    });

    it.each(["", "xx", "DE", "de-AT"])("is the source language for the tag '%s' the app does not offer", (tag) => {
        expect(pageLanguage(tag, ["de", "fr"])).toBe(sourceLanguage);
    });

    describe("read from the document of the browser", () => {
        const originalLang = document.documentElement.lang;
        afterEach(() => {
            document.documentElement.lang = originalLang;
            vi.doUnmock("#lib/words/index.ts");
            vi.resetModules();
        });

        it("is the <html lang> tag when the app offers it", async () => {
            const german = await vi.importActual<typeof import("#lib/words/index.ts")>("#lib/words/index.ts");
            vi.doMock("#lib/words/index.ts", () => ({
                ...german,
                languages: ["de", "fr"],
                loadWords: async () => german.loadWords(german.sourceLanguage),
            }));
            document.documentElement.lang = "fr";
            vi.resetModules();

            const loaded = await import("#lib/words.ts");

            expect(loaded.language).toBe("fr");
        });
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
