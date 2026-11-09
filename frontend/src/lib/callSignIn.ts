import {
    ACCOUNT_PATH,
    AUTH_START_PATH,
    CALL_MODE,
    MODE_QUERY_NAME,
    NO_ACCESS_PATH,
    RETURN_PATH_QUERY_NAME,
    TABLE_ID_PATTERN,
    TABLE_PAGE_PREFIX,
} from "./wire.ts";

export const WATCH_INTERVAL_MILLISECONDS = 500;
export const RECHECK_INTERVAL_MILLISECONDS = 2_000;
export const RECHECK_DURATION_MILLISECONDS = 3 * 60 * 1_000;

const WINDOW_NAME = "skat-sign-in";
const WINDOW_FEATURES = "popup";
const SIGNED_IN_STATUS = 200;
const TABLE_RETURN = new RegExp(`^${TABLE_PAGE_PREFIX}(${TABLE_ID_PATTERN})(?:[?#]|$)`);

/** What the frame shows: the sign-in face, the same with its notice, the waiting face, or the refusal. */
export type CallSignInView = "signed-out" | "unfinished" | "signing-in" | "no-access";

/** The separate window; reading `location` throws while it shows another origin. */
export interface SignInWindow {
    readonly closed: boolean;
    readonly location: { readonly pathname: string };
    close(): void;
}

export interface CallSignInHost {
    open(address: string, name: string, features: string): SignInWindow | null;
    replace(address: string): void;
    fetchStatus(path: string): Promise<number>;
    /** Calls `callback` every `milliseconds` until the returned function is called. */
    every(callback: () => void | Promise<void>, milliseconds: number): () => void;
}

export interface CallSignIn {
    logIn(): void;
    recheck(): void;
    stop(): void;
}

/** The id of the table the page was asked to return to, or null for anything that is not one. */
export function tableIdFromSearch(search: string): string | null {
    const next = new URLSearchParams(search).get(RETURN_PATH_QUERY_NAME);
    return next?.match(TABLE_RETURN)?.[1] ?? null;
}

export function tablePath(tableId: string): string {
    return `${TABLE_PAGE_PREFIX}${tableId}`;
}

export function signInAddress(tableId: string): string {
    return `${AUTH_START_PATH}?${RETURN_PATH_QUERY_NAME}=${encodeURIComponent(tablePath(tableId))}`;
}

function callTableAddress(tableId: string): string {
    return `${tablePath(tableId)}?${MODE_QUERY_NAME}=${CALL_MODE}`;
}

function addressOf(popup: SignInWindow): string | null {
    try {
        return popup.location.pathname;
    } catch {
        return null;
    }
}

export function createCallSignIn(
    tableId: string,
    host: CallSignInHost,
    show: (view: CallSignInView) => void,
): CallSignIn {
    const recheckAsks = RECHECK_DURATION_MILLISECONDS / RECHECK_INTERVAL_MILLISECONDS;
    let round = 0;
    let cancelTimers: (() => void)[] = [];

    function endRound(): number {
        for (const cancel of cancelTimers) {
            cancel();
        }
        cancelTimers = [];
        round += 1;
        return round;
    }

    async function isSignedIn(): Promise<boolean> {
        try {
            return (await host.fetchStatus(ACCOUNT_PATH)) === SIGNED_IN_STATUS;
        } catch {
            return false;
        }
    }

    function recheck(): void {
        const own = endRound();
        let asked = 0;
        const cancel = host.every(async () => {
            asked += 1;
            if (asked >= recheckAsks) {
                cancel();
            }
            if ((await isSignedIn()) && own === round) {
                endRound();
                host.replace(callTableAddress(tableId));
            }
        }, RECHECK_INTERVAL_MILLISECONDS);
        cancelTimers.push(cancel);
    }

    async function popupClosed(own: number): Promise<void> {
        const signedIn = await isSignedIn();
        if (own !== round) {
            return;
        }
        if (signedIn) {
            host.replace(callTableAddress(tableId));
            return;
        }
        show("unfinished");
        recheck();
    }

    function watch(popup: SignInWindow): () => void | Promise<void> {
        return () => {
            if (popup.closed) {
                return popupClosed(endRound());
            }
            const address = addressOf(popup);
            if (address === tablePath(tableId)) {
                popup.close();
                endRound();
                host.replace(callTableAddress(tableId));
            } else if (address === NO_ACCESS_PATH) {
                popup.close();
                endRound();
                show("no-access");
            }
        };
    }

    function logIn(): void {
        endRound();
        show("signing-in");
        const popup = host.open(signInAddress(tableId), WINDOW_NAME, WINDOW_FEATURES);
        if (popup !== null) {
            cancelTimers.push(host.every(watch(popup), WATCH_INTERVAL_MILLISECONDS));
        }
    }

    return { logIn, recheck, stop: () => void endRound() };
}
