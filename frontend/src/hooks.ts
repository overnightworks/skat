import type { Reroute } from "@sveltejs/kit/hooks";
import { CALL_SIGN_IN_PATH } from "#lib/wire.ts";
import { language } from "#lib/words.ts";

// The call sign-in page is prerendered per language and served at one address, so the browser's router finds the
// language's route for it; every other path stays where it is.
export const reroute: Reroute = ({ url }) =>
    url.pathname === CALL_SIGN_IN_PATH ? `/${language}${CALL_SIGN_IN_PATH}` : undefined;
