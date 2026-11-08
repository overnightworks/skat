<script lang="ts">
    import { resolve } from "$app/paths";
    import { page } from "$app/state";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { LegalLinks } from "overnightworks-appkit";
    import { words } from "#lib/words.ts";
    import NewTableButton from "../../NewTableButton.svelte";
    import {
        copyTableLink,
        drawingOrder,
        readTable,
        sitDown,
        standUp,
        watchTable,
        type Outcome,
    } from "../../tables.ts";

    const TAKEN_NOTICE_MILLISECONDS = 4000;

    // The route has an [id] segment, so the parameter is always present.
    const id = $derived(page.params.id as string);
    let outcome = $state<Outcome | null>(null);
    let note = $state("");
    let taken: string | null = $state(null);
    let connected = $state(true);

    // SvelteKit keeps this component when the address changes from one table to another.
    $effect(() => {
        outcome = null;
        connected = true;
        let current = true;
        let stopWatching = (): void => {};
        void readTable(id).then((answer) => {
            if (!current) return;
            outcome = answer;
            if (answer.kind === "table") {
                stopWatching = watchTable(
                    id,
                    (table) => (outcome = { kind: "table", table }),
                    (isConnected) => (connected = isConnected),
                );
            }
        });
        // An answer for an address the person has left must not replace the current table.
        return () => {
            current = false;
            stopWatching();
        };
    });

    const seated = $derived(outcome?.kind === "table" && outcome.table.chairs.some((chair) => chair.is_mine));

    async function copy(): Promise<void> {
        note = (await copyTableLink(id)) ? words.linkCopied : words.linkCopyFailed;
    }

    // A seated or freed chair reaches this page through its stream like every other page's: the answer's table
    // is not the streamed view, so it never replaces it.
    let takenTimer: ReturnType<typeof setTimeout> | undefined;

    async function seat(command: Promise<Outcome>): Promise<void> {
        note = "";
        taken = null;
        const answer = await command;
        if (answer.kind === "taken") {
            taken = answer.holder;
            clearTimeout(takenTimer);
            takenTimer = setTimeout(() => (taken = null), TAKEN_NOTICE_MILLISECONDS);
        } else if (answer.kind !== "table") {
            note = words.commandFailed;
        }
    }
</script>

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
    <title>{`${words.appName}`}</title>
</svelte:head>

<div class="room" data-theme="dark">
    <header class="bar" class:stale={!connected}>
        <a class="wordmark" href={resolve("/(start)")}>{words.appName}</a>
        {#if outcome?.kind === "table"}
            <div class="watchers" title={words.watchers} role="group" aria-label={words.watchers}>
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                >
                    <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
                    <circle cx="12" cy="12" r="3" />
                </svg>
                <span>{outcome.table.watchers}</span>
            </div>
        {/if}
    </header>
    <main class="stage" class:stale={!connected}>
        {#if outcome?.kind === "table"}
            <div class="plaque">
                <span>{words.waitingForPlayers}</span>
                <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
            </div>
            <div class="felt" aria-hidden="true"></div>
            <ul class="chairs">
                {#each drawingOrder(outcome.table.chairs) as chair (chair.seat)}
                    <li class="chair" class:mine={chair.is_mine} class:away={chair.is_away} data-seat={chair.seat}>
                        {#if chair.occupant_name !== null}
                            <span class="tile">
                                <span class="initial" aria-hidden="true">{chair.occupant_name.slice(0, 1)}</span>
                            </span>
                            {#if chair.is_away}
                                <span class="mark away" aria-hidden="true">
                                    <svg
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        stroke-width="2"
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                    >
                                        <path d="M19.5 14.6A7.8 7.8 0 1 1 9.4 4.5a6.3 6.3 0 0 0 10.1 10.1z" />
                                    </svg>
                                </span>
                            {/if}
                        {:else if seated}
                            <span class="tile empty"></span>
                        {:else}
                            <button
                                type="button"
                                class="tile empty free"
                                aria-label={words.sitDown}
                                onclick={() => seat(sitDown(id, chair.seat, crypto.randomUUID()))}
                            >
                                <svg
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    stroke-width="2.2"
                                    stroke-linecap="round"
                                    aria-hidden="true"
                                >
                                    <path d="M12 5v14M5 12h14" />
                                </svg>
                            </button>
                        {/if}
                        <span class="plate"
                            >{chair.occupant_name ?? words.seatFree}{#if chair.is_away}<small class="away-note"
                                    >{words.seatAway}</small
                                >{/if}</span
                        >
                    </li>
                {/each}
            </ul>
            <div class="controls">
                <div class="actions">
                    {#if seated}
                        <button type="button" class="copy" onclick={() => seat(standUp(id, crypto.randomUUID()))}>
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                                stroke-linecap="round"
                                stroke-linejoin="round"
                                aria-hidden="true"
                            >
                                <path d="M4.5 4v16M4.5 13.5h8.5v6.5" />
                                <path d="M18.5 15V4M15 7.5l3.5-3.5L22 7.5" />
                            </svg>
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                            {`${words.standUp}`}
                        </button>
                    {/if}
                    <button type="button" class="copy" onclick={copy}>
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            aria-hidden="true"
                        >
                            <path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2" />
                            <path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2" />
                        </svg>
                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                        {`${words.copyLink}`}
                    </button>
                </div>
                <p class="note" role="status">{note}</p>
            </div>
            {#if taken !== null}
                <p class="notice" role="status">
                    <span class="dot" aria-hidden="true">{taken.slice(0, 1)}</span>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                    <span class="label">{`${words.seatTaken}`}</span>
                    <b>{taken}</b>
                </p>
            {/if}
        {:else if outcome?.kind === "missing"}
            <section class="panel">
                <h1>{words.tableNotFound}</h1>
                <NewTableButton />
            </section>
        {:else if outcome?.kind === "failed"}
            <section class="panel" role="alert">
                <h1>{words.tableLoadFailed}</h1>
                <p>{words.tableLoadFailedHint}</p>
            </section>
        {/if}
    </main>
    <div class="reconnect" role="status" hidden={connected}><span class="spin"></span>{words.reconnecting}</div>
    <footer class="legal">
        <LegalLinks links={LEGAL_LINKS} />
    </footer>
</div>
