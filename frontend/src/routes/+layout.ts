import type { LayoutLoad } from "./$types";
import { loadKitWords } from "overnightworks-design/words";
import { language as pageLanguage } from "#lib/words.ts";
import { loadWords } from "#lib/words/index.ts";

// One `load` for every page: the prerendered sign-in pages and the client-rendered ones get the words alike. A route
// that carries a language is prerendered in it; any other page speaks the language of `<html lang>`.
export const load: LayoutLoad = async ({ params }) => {
    const language = params.language ?? pageLanguage;
    return { kitWords: await loadKitWords(language), words: await loadWords(language) };
};
