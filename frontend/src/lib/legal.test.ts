import { describe, expect, it } from "vitest";
import { legalLinks } from "#lib/legal.ts";
import { languages, loadWords } from "#lib/words/index.ts";

describe("legalLinks", () => {
    it.each(languages)(
        "gives every %s link an absolute https address with a fragment and a distinct non-empty label",
        async (language) => {
            const links = legalLinks(await loadWords(language));

            for (const link of links) {
                const address = new URL(link.href);
                expect(address.protocol).toBe("https:");
                expect(address.hash.length).toBeGreaterThan(1);
                expect(link.label.trim()).not.toBe("");
            }
            const labels = links.map((link) => link.label);
            expect(new Set(labels).size).toBe(labels.length);
        },
    );

    it("reads the labels in the language it is given and leads to the same addresses in every language", async () => {
        const [first, ...others] = await Promise.all(
            languages.map(async (language) => legalLinks(await loadWords(language))),
        );

        expect(first?.map((link) => link.label)).not.toEqual(others[0]?.map((link) => link.label));
        for (const other of others) {
            expect(other.map((link) => link.href)).toEqual(first?.map((link) => link.href));
        }
    });
});
