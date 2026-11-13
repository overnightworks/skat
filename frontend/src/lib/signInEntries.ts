import { languages } from "./words/index.ts";

// The prerender writes each sign-in page once per language the catalogs offer.
export const entries = () => languages.map((language) => ({ language }));
