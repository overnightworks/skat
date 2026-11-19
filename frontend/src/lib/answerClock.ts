// The whole seconds until `until`, never below zero; `now` and `until` are on the same wall clock.
export function secondsLeft(until: string, now: number): number {
    return Math.max(0, Math.ceil((Date.parse(until) - now) / 1000));
}

// Minutes and seconds as a clock shows them: 0:42.
export function clockText(seconds: number): string {
    return `${String(Math.floor(seconds / 60))}:${String(seconds % 60).padStart(2, "0")}`;
}
