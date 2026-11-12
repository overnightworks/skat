import type { KitLanguage } from "overnightworks-design/words";
import { languages } from "./words/index.ts";

// The kit must speak every language the app offers; a language it lacks fails the type check.
export const kitLanguages = languages satisfies readonly KitLanguage[];

// The one import of every component. The page-side loader that picks a language by `<html lang>` replaces this line.
export { language, words, type Key } from "./words/de.ts";
