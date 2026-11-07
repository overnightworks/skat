<script lang="ts">
    import { resolve } from "$app/paths";
    import { page } from "$app/state";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { LegalLinks } from "overnightworks-appkit";
    import NewTableButton from "../../NewTableButton.svelte";
    import { copyTableLink, drawingOrder, readTable, type Outcome } from "../../tables.ts";

    const id = $derived(page.params.id ?? "");
    let outcome: Outcome | null = $state(null);
    let copyNote = $state("");

    // SvelteKit keeps this component when the address changes from one table to another.
    $effect(() => {
        outcome = null;
        let current = true;
        void readTable(id).then((answer) => {
            if (current) outcome = answer;
        });
        // An answer for an address the person has left must not replace the current table.
        return () => {
            current = false;
        };
    });

    async function copy(): Promise<void> {
        copyNote = (await copyTableLink(id)) ? "Link kopiert" : "Der Link ließ sich nicht kopieren";
    }
</script>

<svelte:head>
    <title>Skat</title>
</svelte:head>

<div class="room" data-theme="dark" lang="de">
    <header class="bar">
        <a class="wordmark" href={resolve("/(start)")}>Skat</a>
    </header>
    <main class="stage">
        {#if outcome?.kind === "table"}
            <div class="plaque">
                <span>Warte auf Mitspieler</span>
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
                        <span class="plate">{chair.occupant_name ?? "Frei"}</span>
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
                    Link kopieren
                </button>
                <p class="note" role="status">{copyNote}</p>
            </div>
        {:else if outcome?.kind === "missing"}
            <section class="panel">
                <h1>Tisch nicht gefunden</h1>
                <NewTableButton />
            </section>
        {:else if outcome?.kind === "failed"}
            <section class="panel" role="alert">
                <h1>Der Tisch lässt sich gerade nicht laden</h1>
                <p>Lade die Seite neu, um es noch einmal zu versuchen.</p>
            </section>
        {/if}
    </main>
    <footer class="legal">
        <LegalLinks links={LEGAL_LINKS} />
    </footer>
</div>
