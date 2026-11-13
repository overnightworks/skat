<script lang="ts">
    import { gameRows, type GameRow } from "#lib/series.ts";
    import { words } from "#lib/words.ts";

    import { readSeriesList } from "../../routes/(start)/tables.ts";

    // The quiet mark on the felt; a tap opens the list of every game of the series, which reads again whenever the table
    // moves on while it is open.
    const { id, text, version }: { id: string; text: string; version: number } = $props();

    let sheet: HTMLDialogElement | undefined = $state();
    let open = $state(false);
    let rows = $state<GameRow[] | null>(null);
    let failed = $state(false);

    const wanted = $derived(open ? { id, version } : null);

    $effect(() => {
        if (wanted === null) return;
        let current = true;
        void readSeriesList(wanted.id).then((entries) => {
            if (!current) return;
            failed = entries === null;
            rows = entries === null ? rows : gameRows(entries);
        });
        return () => {
            current = false;
        };
    });
</script>

<button
    type="button"
    class="series-count"
    class:unfolded={open}
    aria-expanded={open}
    aria-label={words["table.seriesList"]}
    onclick={() => {
        rows = null;
        failed = false;
        open = true;
        sheet?.showModal();
    }}
>
    <span>{text}</span>
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.4"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path d="M6 9l6 6 6-6" />
    </svg>
</button>
<dialog
    bind:this={sheet}
    class="game-list"
    aria-label={words["table.seriesList"]}
    onclose={() => {
        open = false;
    }}
    onclick={(event) => {
        if (event.target === sheet) sheet.close();
    }}
>
    <div class="panel-body">
        <h3>{words["table.seriesListTitle"]}</h3>
        <ol class="rows">
            {#each rows ?? [] as row (row.number)}
                <li class="grow">
                    <span class="nr">{row.number}</span>
                    <span class="dot" aria-hidden="true">{row.initial}</span>
                    <span class="txt">
                        <b>{row.name}</b>
                        {#if row.line !== null}<small>{row.line}</small>{/if}
                    </span>
                    <span class="val">{row.value}</span>
                    <span class="gain" class:minus={row.lost}>{row.gain}</span>
                </li>
            {/each}
        </ol>
        {#if failed}
            <p class="empty" role="alert">{words["table.seriesListFailed"]}</p>
        {:else if rows?.length === 0}
            <p class="empty">{words["table.seriesListEmpty"]}</p>
        {/if}
    </div>
</dialog>
