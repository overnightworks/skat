import { defineParams } from "@sveltejs/kit/params";
import { languages } from "#lib/words/index.ts";

// The sign-in routes carry the language the build prerenders them in.
export const params = defineParams({
    language: (param) => languages.find((language) => language === param),
});
