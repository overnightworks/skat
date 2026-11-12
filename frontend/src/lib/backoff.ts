// The one owner of how long a page waits before it asks again after a connection failed: the table page's stream
// reader and the page that stands in for a start page that could not load both wait by it.

const FIRST_RETRY_MILLISECONDS = 1_000;
const RETRY_LIMIT_MILLISECONDS = 30_000;

// Doubles from the first retry to the limit, and each wait lies between half and all of that, so that
// many pages after one restart do not all ask again at the same moment.
export function retryDelayMilliseconds(failedAttempts: number): number {
    const full = Math.min(RETRY_LIMIT_MILLISECONDS, FIRST_RETRY_MILLISECONDS * 2 ** failedAttempts);
    return full / 2 + (Math.random() * full) / 2;
}
