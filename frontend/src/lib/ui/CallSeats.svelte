<script lang="ts">
    import { onMount, untrack } from "svelte";
    import type { Table } from "../../routes/(start)/tables.ts";
    import { retryDelayMilliseconds } from "#lib/backoff.ts";
    import { browserCallHost, greetCall, type CallChannel } from "#lib/callFrame.ts";
    import {
        acceptedPlacements,
        holdOf,
        holesPath,
        occupancyOf,
        openSeats,
        postedSeats,
        readPersonKeys,
        seatsMessage,
        type PostedSeat,
        type SeatKeys,
        type TileReading,
    } from "#lib/callSeats.ts";

    // The framed table's side of the call: it greets the call, tells it where each chair's tile lies, takes its answer
    // `placed` and makes the chairs the call placed see-through. It draws nothing itself; the rules are in callSeats.ts.
    // While the page is greeted and visible, every animation frame reads the tiles, so a move without a resize is
    // caught; a posted payload and a written clip path are each posted or written only when they differ from the last.
    const {
        tableId,
        table,
        ongreeted,
    }: {
        tableId: string;
        /** The table the page shows, or null while it shows none. */
        table: Table | null;
        /** Runs once, at the call's first valid hello. */
        ongreeted: () => void;
    } = $props();

    // The chairs of a live table; an ended table has none to tell.
    const view = $derived(table !== null && table.ended === null ? table : null);
    const CHAIRS = ".room .chair[data-seat]";
    const host = browserCallHost();
    const clipsWritten = new WeakMap<Element, string>();
    let channel: CallChannel | null = null;
    let greeted = $state(false);
    let placed: ReadonlySet<string> = new Set();
    let posted: readonly PostedSeat[] = [];
    let postedText = "";
    let fullPostWanted = false;
    let frame: number | undefined;
    let keys: SeatKeys | null = null;
    let keysFailed = false;
    let failedReads = 0;
    // An object: what happens during a request is not narrowed away by the code that waits for it.
    const reads = { running: false, again: false, leaving: false };
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const corner = (text: string): number => (text.endsWith("px") ? Number.parseFloat(text) : Number.NaN);

    function readTiles(chairs: Table["chairs"], read: SeatKeys): TileReading[] {
        const readings: TileReading[] = [];
        for (const chair of document.querySelectorAll<HTMLElement>(CHAIRS)) {
            const seat = Number(chair.dataset.seat);
            const key = read.keys.get(seat);
            const facts = chairs.find((each) => each.seat === seat);
            const tile = chair.querySelector<HTMLElement>(".tile");
            if (key === undefined || facts === undefined || tile === null) continue;
            const rect = tile.getBoundingClientRect();
            const style = getComputedStyle(tile);
            readings.push({
                seat,
                key,
                occupancy: occupancyOf(facts),
                rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                shape: style.getPropertyValue("--call-tile-shape").trim(),
                radii: {
                    tl: corner(style.borderTopLeftRadius),
                    tr: corner(style.borderTopRightRadius),
                    br: corner(style.borderBottomRightRadius),
                    bl: corner(style.borderBottomLeftRadius),
                },
            });
        }
        return readings;
    }

    function post(seats: readonly PostedSeat[]): void {
        const message = seatsMessage(tableId, seats);
        const text = JSON.stringify(message);
        if (!fullPostWanted && text === postedText) return;
        channel?.post(message);
        posted = seats;
        postedText = text;
        fullPostWanted = false;
    }

    function paintHoles(current: Table | null, keysAreCurrent: boolean): void {
        const occupancyNow = new Map((current?.chairs ?? []).map((chair) => [chair.seat, occupancyOf(chair)]));
        const open = openSeats({ posted, placed, occupancyNow, current: keysAreCurrent });
        const openSeatNumbers = new Set(open.map(({ seat }) => seat));
        for (const chair of document.querySelectorAll<HTMLElement>(CHAIRS)) {
            chair.toggleAttribute("data-see-through", openSeatNumbers.has(Number(chair.dataset.seat)));
        }
        const holes = open.map(({ entry }) => entry);
        for (const backdrop of document.querySelectorAll<HTMLElement>("[data-call-backdrop]")) {
            const clip = holes.length === 0 ? "" : holesPath(backdrop.getBoundingClientRect(), holes);
            if (clip === (clipsWritten.get(backdrop) ?? "")) continue;
            clipsWritten.set(backdrop, clip);
            if (clip === "") backdrop.style.removeProperty("clip-path");
            else backdrop.style.setProperty("clip-path", clip);
        }
    }

    // The boxes go out only while the keys are those of the view; a failed read posts an empty list, and keys of another
    // version leave the call its last layout.
    function flush(): void {
        const hold = holdOf(keysFailed, keys, view?.version ?? null);
        if (hold === "failed") post([]);
        else if (hold === "current" && view !== null && keys !== null) post(postedSeats(readTiles(view.chairs, keys)));
        paintHoles(view, hold === "current");
    }

    function runFrames(): void {
        if (frame !== undefined || !greeted || document.visibilityState !== "visible") return;
        frame = requestAnimationFrame(() => {
            frame = undefined;
            flush();
            runFrames();
        });
    }

    async function readKeys(): Promise<void> {
        if (reads.running) {
            reads.again = true;
            return;
        }
        reads.running = true;
        clearTimeout(retryTimer);
        const read = await readPersonKeys(host.fetch.bind(host), tableId);
        reads.running = false;
        if (reads.leaving) return;
        if (read === null) {
            keysFailed = true;
            retryTimer = setTimeout(() => void readKeys(), retryDelayMilliseconds(failedReads));
            failedReads += 1;
        } else {
            keys = read;
            keysFailed = false;
            failedReads = 0;
        }
        if (reads.again) {
            reads.again = false;
            void readKeys();
        }
    }

    function hello(first: boolean): void {
        placed = new Set();
        fullPostWanted = true;
        if (first) {
            greeted = true;
            ongreeted();
        }
        runFrames();
    }

    function seeWhetherVisible(): void {
        if (document.visibilityState === "visible") {
            fullPostWanted = true;
            runFrames();
        } else if (frame !== undefined) {
            cancelAnimationFrame(frame);
            frame = undefined;
        }
    }

    onMount(() => {
        channel = greetCall(
            untrack(() => tableId),
            host,
            {
                onHello: hello,
                onPlaced: (placedKeys) => {
                    placed = acceptedPlacements(placedKeys, posted);
                },
            },
        );
        document.addEventListener("visibilitychange", seeWhetherVisible);
        return () => {
            reads.leaving = true;
            channel?.stop();
            document.removeEventListener("visibilitychange", seeWhetherVisible);
            if (frame !== undefined) cancelAnimationFrame(frame);
            clearTimeout(retryTimer);
        };
    });

    // A new version of the view asks for the keys of the newest; one request runs at a time.
    const version = $derived(view?.version ?? null);
    $effect(() => {
        if (greeted && version !== null) untrack(() => void readKeys());
    });
</script>
