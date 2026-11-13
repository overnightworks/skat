import type { KitLanguage } from "overnightworks-design/words";
import type { Words } from "./words/de.ts";
import { languages, loadWords, sourceLanguage, type Language } from "./words/index.ts";

// The kit must speak every language the app offers; a language it lacks fails the type check.
export const kitLanguages = languages satisfies readonly KitLanguage[];

// The language the page speaks: the tag of `<html lang>` when the app offers it, else the source language.
export function pageLanguage<Offered extends string>(tag: string, offered: readonly Offered[]): Offered | Language {
    return offered.find((each) => each === tag) ?? sourceLanguage;
}

// Where no document exists (the build's prerender, a unit test) the page speaks the source language.
export const language: Language = pageLanguage(
    typeof document === "undefined" ? "" : document.documentElement.lang,
    languages,
);

// The one import of every component. The words load once, here, so every importer sees them before it runs.
export const words: Words = await loadWords(language);
export type Key = keyof Words;

// Names listed in the page's language: "Anna, Ben und Carla".
export const listFormat = new Intl.ListFormat(language, { style: "long", type: "conjunction" });
