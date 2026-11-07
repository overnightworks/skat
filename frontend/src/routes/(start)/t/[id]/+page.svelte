<script lang="ts">
    import { resolve } from "$app/paths";
    import { page } from "$app/state";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { LegalLinks } from "overnightworks-appkit";
    import { words } from "#lib/words.ts";
    import NewTableButton from "../../NewTableButton.svelte";
    import { copyTableLink, drawingOrder, readTable, watchTable, type Outcome } from "../../tables.ts";

    // The route has an [id] segment, so the parameter is always present.
    const id = $derived(page.params.id as string);
    let outcome: Outcome | null = $state(null);
    let copyNote = $state("");
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

    async function copy(): Promise<void> {
        copyNote = (await copyTableLink(id)) ? words.linkCopied : words.linkCopyFailed;
    }
</script>

<svelte:head>
    <title>{words.appName}</title>
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
                    <li class="chair" class:mine={chair.is_mine} data-seat={chair.seat}>
                        <span class="tile" class:empty={chair.occupant_name === null}>
                            {#if chair.occupant_name !== null}
                                <span class="initial" aria-hidden="true">{chair.occupant_name.slice(0, 1)}</span>
                            {/if}
                        </span>
                        <span class="plate">{chair.occupant_name ?? words.seatFree}</span>
                    </li>
                {/each}
            </ul>
            <div class="controls">
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
                    {words.copyLink}
                </button>
                <p class="note" role="status">{copyNote}</p>
            </div>
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
