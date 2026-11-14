const QUERY = "(prefers-reduced-motion: reduce)";

// Reduced until the device has answered, so a page that is not yet in a browser moves nothing.
const device = $state({ reduces: true });
let watched = false;

/** Reads what the device asks for motion and follows it when the player changes it; the page asks once. */
export function watchDeviceMotion(): void {
    if (watched) return;
    watched = true;
    const query = window.matchMedia(QUERY);
    device.reduces = query.matches;
    query.addEventListener("change", (event) => {
        device.reduces = event.matches;
    });
}

export function deviceReducesMotion(): boolean {
    return device.reduces;
}
