<script lang="ts">
    import { onMount, untrack } from "svelte";
    import type { Outcome, Table } from "../../routes/(start)/tables.ts";
    import { retryDelayMilliseconds } from "#lib/backoff.ts";
    import { browserCallHost, greetCall, type CallChannel } from "#lib/callFrame.ts";
    import {
        acceptedPlacements,
        holdOf,
        holesPath,
        keysFitView,
        occupancyBySeat,
        occupancyOf,
        openSeats,
        postedSeats,
        readPersonKeys,
        seatsMessage,
        shownAsInView,
        shownTable,
        type PostedSeat,
        type SeatKeys,
        type TileReading,
    } from "#lib/callSeats.ts";

    // The framed table's side of the call: it greets the call, tells it where each chair's tile lies, takes its answer
    // `placed` and makes the chairs the call placed see-through. It draws nothing itself; the rules are in callSeats.ts.
    // Who sits and which version the keys must match follow the newest table the stream brought, at once; the table the
    // page shows may lag behind it while an auction is told or a closing waits, and only the tiles are read from that.
    // While the page is greeted and visible, every animation frame reads the tiles, so a move without a resize is
    // caught; a posted payload and a written clip path are each posted or written only when they differ from the last.
    const {
        tableId,
        outcome,
        newest,
        ongreeted,
    }: {
        tableId: string;
        /** What the page shows: the table it has, or that none is there. */
        outcome: Outcome | null;
        /** The newest table the page has received, shown or not, or null while it has none. */
        newest: Table | null;
        /** Runs once, at the call's first valid hello. */
        ongreeted: () => void;
    } = $props();

    const table = $derived(shownTable(outcome));
    const missing = $derived(outcome?.kind === "missing");
    // The chairs of a live table; an ended table has none to tell, and the call hears that, as it does of a gone one.
    const view = $derived(newest !== null && newest.ended === null ? newest : null);
    const closed = $derived(missing || (newest !== null && view === null));
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
    // What each chair held in the view whose version the keys have, once the page has seen that view.
    let keyedOccupancy: ReadonlyMap<number, string> | null = null;
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

    function paintHoles(current: Table | null): void {
        const occupancyNow = occupancyBySeat(current?.chairs ?? []);
        const open = openSeats({ posted, placed, occupancyNow });
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

    // The boxes go out only while the keys fit the view; a failed read or a table that ended or is gone posts an empty
    // list, and keys that do not fit leave the call its last layout, whose holes stay open for each chair that holds
    // what it held when it was posted.
    function flush(): void {
        if (keyedOccupancy === null && keys !== null && view !== null && keys.version === view.version) {
            keyedOccupancy = occupancyBySeat(view.chairs);
        }
        const hold = holdOf({ closed, failed: keysFailed, fits: keysFitView({ keys, keyedOccupancy, view }) });
        if (hold === "closed" || hold === "failed") post([]);
        else if (hold === "current" && view !== null && table !== null && keys !== null) {
            const tiles = readTiles(table.chairs, keys);
            post(postedSeats(shownAsInView(tiles, occupancyBySeat(view.chairs))));
        }
        paintHoles(view);
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
            keyedOccupancy = view?.version === read.version ? occupancyBySeat(view.chairs) : null;
            keysFailed = false;
            failedReads = 0;
        }
        if (reads.again) {
            reads.again = false;
            void readKeys();
        }
    }

    // A view that leaves every chair as it was needs no new keys, unless the last read failed.
    function readKeysUnlessTheyFit(): void {
        if (keysFailed || !keysFitView({ keys, keyedOccupancy, view })) void readKeys();
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
        if (greeted && version !== null) untrack(readKeysUnlessTheyFit);
    });
</script>
