import { describe, expect, it, vi, type Mock } from "vitest";
import {
    createCallSignIn,
    RECHECK_DURATION_MILLISECONDS,
    RECHECK_INTERVAL_MILLISECONDS,
    tableIdFromSearch,
    WATCH_INTERVAL_MILLISECONDS,
    type CallSignInHost,
    type CallSignInView,
    type SignInWindow,
} from "./callSignIn.ts";
import {
    AUTH_START_PATH,
    CALL_MODE,
    MODE_QUERY_NAME,
    NO_ACCESS_PATH,
    RETURN_PATH_QUERY_NAME,
    TABLE_PAGE_PREFIX,
} from "./wire.ts";

const TABLE_ID = "0123456789abcdef0123456789abcdef";
const TABLE_PATH = `${TABLE_PAGE_PREFIX}${TABLE_ID}`;
const ORIGIN = "https://skat.test";

interface Timer {
    callback: () => void | Promise<void>;
    milliseconds: number;
    cancelled: boolean;
}

interface FakeWindow extends SignInWindow {
    closed: boolean;
    close: Mock<() => void>;
}

function signInWindow(pathname: string | Error): FakeWindow {
    const window: FakeWindow = {
        closed: false,
        close: vi.fn<() => void>(() => {
            window.closed = true;
        }),
        get location(): { pathname: string } {
            if (pathname instanceof Error) {
                throw pathname;
            }
            return { pathname };
        },
    };
    return window;
}

function arrange(options: { opened?: SignInWindow | null; accountStatus?: number | Error } = {}) {
    const views: CallSignInView[] = [];
    const timers: Timer[] = [];
    const answers: (number | Error)[] = [];
    const host = {
        open: vi.fn<CallSignInHost["open"]>(() => options.opened ?? null),
        replace: vi.fn<CallSignInHost["replace"]>(),
        fetchStatus: vi.fn<CallSignInHost["fetchStatus"]>(() => {
            const answer = answers.length > 0 ? answers.shift() : options.accountStatus;
            return typeof answer === "number" ? Promise.resolve(answer) : Promise.reject(answer ?? new Error("none"));
        }),
        every: vi.fn<CallSignInHost["every"]>((callback, milliseconds) => {
            const timer = { callback, milliseconds, cancelled: false };
            timers.push(timer);
            return () => {
                timer.cancelled = true;
            };
        }),
    };
    const signIn = createCallSignIn(TABLE_ID, host, (view) => views.push(view));
    const live = (milliseconds: number) =>
        timers.filter((timer) => !timer.cancelled && timer.milliseconds === milliseconds);
    const fire = async (milliseconds: number) => {
        for (const timer of live(milliseconds)) {
            await timer.callback();
        }
    };
    return { signIn, host, views, fire, live, answers };
}

const crossOrigin = () => new DOMException("blocked a frame", "SecurityError");

describe("tableIdFromSearch", () => {
    const nextOf = (next: string) => `?${RETURN_PATH_QUERY_NAME}=${encodeURIComponent(next)}`;

    it.each([TABLE_PATH, `${TABLE_PATH}?${MODE_QUERY_NAME}=${CALL_MODE}`])("keeps the id of %s", (next) => {
        expect(tableIdFromSearch(nextOf(next))).toBe(TABLE_ID);
    });

    it.each([
        ["no query", ""],
        ["no return address", "?other=1"],
        ["a foreign address", `https://evil.test${TABLE_PATH}`],
        ["a protocol-relative address", `//evil.test${TABLE_PATH}`],
        ["a script address", "javascript:alert(1)"],
        ["a path that is no table", "/logout"],
        ["a path that climbs out of the tables", `${TABLE_PAGE_PREFIX}../logout`],
        ["a table's sub-path", `${TABLE_PATH}/events`],
        ["an id that is too short", `${TABLE_PAGE_PREFIX}${TABLE_ID.slice(1)}`],
        ["an id that is too long", `${TABLE_PATH}0`],
        ["an id with capital letters", `${TABLE_PAGE_PREFIX}${TABLE_ID.toUpperCase()}`],
        ["a prefix inside the address", `/x${TABLE_PATH}`],
    ])("keeps no id of %s", (_name, next) => {
        expect(tableIdFromSearch(nextOf(next))).toBeNull();
    });
});

describe("a tap on Log in", () => {
    it("opens the sign-in start in a named popup that returns to the plain table, and shows the waiting face", () => {
        const { signIn, host, views } = arrange({ opened: signInWindow(crossOrigin()) });

        signIn.logIn();

        const [address = "", name, features] = host.open.mock.calls[0] ?? [];
        const opened = new URL(address, ORIGIN);
        expect(opened.pathname).toBe(AUTH_START_PATH);
        expect(opened.searchParams.get(RETURN_PATH_QUERY_NAME)).toBe(TABLE_PATH);
        expect(name).not.toBe("");
        expect(features).toContain("popup");
        expect(views).toEqual(["signing-in"]);
    });

    it("waits while the popup shows another origin", async () => {
        const { signIn, fire, host, views } = arrange({ opened: signInWindow(crossOrigin()) });
        signIn.logIn();

        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(views).toEqual(["signing-in"]);
        expect(host.replace).not.toHaveBeenCalled();
        expect(host.fetchStatus).not.toHaveBeenCalled();
    });

    it("waits while the popup shows a page of Skat that is neither the table nor the refusal", async () => {
        const { signIn, fire, host, views } = arrange({ opened: signInWindow("/auth/callback") });
        signIn.logIn();

        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(views).toEqual(["signing-in"]);
        expect(host.replace).not.toHaveBeenCalled();
    });

    it("closes the popup and takes the frame to the call-mode table when the popup reaches the table", async () => {
        const popup = signInWindow(TABLE_PATH);
        const { signIn, fire, host, live } = arrange({ opened: popup });
        signIn.logIn();

        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(popup.close).toHaveBeenCalledOnce();
        const replaced = new URL(host.replace.mock.calls[0]?.[0] ?? "", ORIGIN);
        expect(replaced.pathname).toBe(TABLE_PATH);
        expect(replaced.searchParams.get(MODE_QUERY_NAME)).toBe(CALL_MODE);
        expect(live(WATCH_INTERVAL_MILLISECONDS)).toEqual([]);
    });

    it("closes the popup and shows No access when the popup reaches the refusal", async () => {
        const popup = signInWindow(NO_ACCESS_PATH);
        const { signIn, fire, host, views, live } = arrange({ opened: popup });
        signIn.logIn();

        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(popup.close).toHaveBeenCalledOnce();
        expect(views).toEqual(["signing-in", "no-access"]);
        expect(host.replace).not.toHaveBeenCalled();
        expect(live(WATCH_INTERVAL_MILLISECONDS)).toEqual([]);
    });

    it("takes the frame to the table when the popup is closed and the account answers 200", async () => {
        const popup = signInWindow(crossOrigin());
        const { signIn, fire, host, views } = arrange({ opened: popup, accountStatus: 200 });
        signIn.logIn();
        popup.closed = true;

        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(new URL(host.replace.mock.calls[0]?.[0] ?? "", ORIGIN).pathname).toBe(TABLE_PATH);
        expect(views).toEqual(["signing-in"]);
    });

    it.each([
        ["answers 401", 401],
        ["fails", new Error("offline")],
    ])("shows the notice when the popup is closed and the account %s", async (_name, accountStatus) => {
        const popup = signInWindow(crossOrigin());
        const { signIn, fire, host, views, live } = arrange({ opened: popup, accountStatus });
        signIn.logIn();
        popup.closed = true;

        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(views).toEqual(["signing-in", "unfinished"]);
        expect(host.replace).not.toHaveBeenCalled();
        expect(live(WATCH_INTERVAL_MILLISECONDS)).toEqual([]);
        expect(live(RECHECK_INTERVAL_MILLISECONDS)).toHaveLength(1);
    });

    it("brings the table when a sign-in finishes after the notice, within the re-check", async () => {
        const popup = signInWindow(crossOrigin());
        const { signIn, fire, host, answers } = arrange({ opened: popup });
        answers.push(401, 401, 200);
        signIn.logIn();
        popup.closed = true;
        await fire(WATCH_INTERVAL_MILLISECONDS);

        await fire(RECHECK_INTERVAL_MILLISECONDS);
        expect(host.replace).not.toHaveBeenCalled();
        await fire(RECHECK_INTERVAL_MILLISECONDS);

        expect(new URL(host.replace.mock.calls[0]?.[0] ?? "", ORIGIN).pathname).toBe(TABLE_PATH);
    });

    it("ends the re-check after its duration", async () => {
        const popup = signInWindow(crossOrigin());
        const { signIn, fire, host, live } = arrange({ opened: popup, accountStatus: 401 });
        signIn.logIn();
        popup.closed = true;
        await fire(WATCH_INTERVAL_MILLISECONDS);
        const asks = RECHECK_DURATION_MILLISECONDS / RECHECK_INTERVAL_MILLISECONDS;

        for (let ask = 0; ask < asks; ask += 1) {
            await fire(RECHECK_INTERVAL_MILLISECONDS);
        }

        expect(host.fetchStatus).toHaveBeenCalledTimes(1 + asks);
        expect(live(RECHECK_INTERVAL_MILLISECONDS)).toEqual([]);
    });

    it("ends an earlier re-check and opens a new popup on the next tap", async () => {
        const popup = signInWindow(crossOrigin());
        const { signIn, fire, host, live } = arrange({ opened: popup, accountStatus: 401 });
        signIn.logIn();
        popup.closed = true;
        await fire(WATCH_INTERVAL_MILLISECONDS);

        signIn.logIn();

        expect(host.open).toHaveBeenCalledTimes(2);
        expect(live(RECHECK_INTERVAL_MILLISECONDS)).toEqual([]);
        expect(live(WATCH_INTERVAL_MILLISECONDS)).toHaveLength(1);
    });

    it("ends the watch of an earlier popup on the next tap", () => {
        const { signIn, live } = arrange({ opened: signInWindow(crossOrigin()) });
        signIn.logIn();

        signIn.logIn();

        expect(live(WATCH_INTERVAL_MILLISECONDS)).toHaveLength(1);
    });

    it("ignores an answer that arrives after a newer tap", async () => {
        const popup = signInWindow(crossOrigin());
        const { signIn, host, views } = arrange({ opened: popup });
        let answer: (status: number) => void = () => undefined;
        host.fetchStatus.mockImplementationOnce(() => new Promise<number>((resolve) => (answer = resolve)));
        signIn.logIn();
        popup.closed = true;
        const asking = host.every.mock.calls[0]?.[0]();
        signIn.logIn();

        answer(401);
        await asking;

        expect(views).toEqual(["signing-in", "signing-in"]);
        expect(host.replace).not.toHaveBeenCalled();
    });
});

describe("a window that does not come up", () => {
    it("keeps the waiting face without any watch", () => {
        const { signIn, views, live } = arrange({ opened: null });

        signIn.logIn();

        expect(views).toEqual(["signing-in"]);
        expect(live(WATCH_INTERVAL_MILLISECONDS)).toEqual([]);
        expect(live(RECHECK_INTERVAL_MILLISECONDS)).toEqual([]);
    });

    it("brings the table when a sign-in finished in the plain link's tab", async () => {
        const { signIn, fire, host, views } = arrange({ opened: null, accountStatus: 200 });
        signIn.logIn();

        signIn.recheck();
        await fire(RECHECK_INTERVAL_MILLISECONDS);

        expect(new URL(host.replace.mock.calls[0]?.[0] ?? "", ORIGIN).pathname).toBe(TABLE_PATH);
        expect(views).toEqual(["signing-in"]);
    });

    it("keeps the waiting face while the tab's sign-in has not finished", async () => {
        const { signIn, fire, views } = arrange({ opened: null, accountStatus: 401 });
        signIn.logIn();
        signIn.recheck();

        await fire(RECHECK_INTERVAL_MILLISECONDS);

        expect(views).toEqual(["signing-in"]);
    });

    it("restarts the re-check on a second tap of the plain link", () => {
        const { signIn, live } = arrange({ opened: null, accountStatus: 401 });
        signIn.logIn();

        signIn.recheck();
        signIn.recheck();

        expect(live(RECHECK_INTERVAL_MILLISECONDS)).toHaveLength(1);
    });
});

describe("a tap on the plain link while the window is open", () => {
    it("keeps watching the window and shows No access when a non-member finishes in it", async () => {
        const popup = signInWindow(NO_ACCESS_PATH);
        const { signIn, fire, host, views } = arrange({ opened: popup, accountStatus: 401 });
        signIn.logIn();

        signIn.recheck();
        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(popup.close).toHaveBeenCalled();
        expect(views).toEqual(["signing-in", "no-access"]);
        expect(host.replace).not.toHaveBeenCalled();
    });

    it("still brings the notice when the window is closed early", async () => {
        const popup = signInWindow(crossOrigin());
        const { signIn, fire, views } = arrange({ opened: popup, accountStatus: 401 });
        signIn.logIn();
        signIn.recheck();

        popup.closed = true;
        await fire(WATCH_INTERVAL_MILLISECONDS);

        expect(views).toEqual(["signing-in", "unfinished"]);
    });
});

describe("a frame that unloads", () => {
    it("ends every timer and ignores a late answer", async () => {
        const popup = signInWindow(crossOrigin());
        const { signIn, host, views, live } = arrange({ opened: popup });
        let answer: (status: number) => void = () => undefined;
        host.fetchStatus.mockImplementationOnce(() => new Promise<number>((resolve) => (answer = resolve)));
        signIn.logIn();
        popup.closed = true;
        const asking = host.every.mock.calls[0]?.[0]();

        signIn.stop();
        answer(200);
        await asking;

        expect(live(WATCH_INTERVAL_MILLISECONDS)).toEqual([]);
        expect(live(RECHECK_INTERVAL_MILLISECONDS)).toEqual([]);
        expect(host.replace).not.toHaveBeenCalled();
        expect(views).toEqual(["signing-in"]);
    });
});
