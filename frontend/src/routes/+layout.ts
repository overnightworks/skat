import { loadKitWords } from "overnightworks-design/words";
import { language } from "#lib/words.ts";

// One `load` for every page: the prerendered sign-in pages and the client-rendered ones get the kit's words alike.
export const load = async () => ({ kitWords: await loadKitWords(language) });
