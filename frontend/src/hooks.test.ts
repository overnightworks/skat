import { describe, expect, it } from "vitest";
import { reroute } from "./hooks.ts";
import { CALL_SIGN_IN_PATH, LOGOUT_PATH } from "#lib/wire.ts";
import { language } from "#lib/words.ts";

const event = (path: string) => ({ url: new URL(path, "https://skat.example"), fetch });

describe("reroute", () => {
    it("leads the call sign-in address to the route of the page's language", () => {
        expect(reroute(event(`${CALL_SIGN_IN_PATH}?next=%2Ft%2Fabc`))).toBe(`/${language}${CALL_SIGN_IN_PATH}`);
    });

    it.each(["/", "/login", LOGOUT_PATH, `${CALL_SIGN_IN_PATH}/more`, `/de${CALL_SIGN_IN_PATH}`])(
        "leaves the path %s alone",
        (path) => {
            expect(reroute(event(path))).toBeUndefined();
        },
    );
});
