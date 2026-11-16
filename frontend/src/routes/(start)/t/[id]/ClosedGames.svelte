<script lang="ts">
    import { page } from "$app/state";
    import { gameRows, type GameRow } from "#lib/series.ts";
    import GameRowFace from "#lib/ui/GameRowFace.svelte";
    import GameSheet from "#lib/ui/GameSheet.svelte";
    import { words } from "#lib/words.ts";
    import { readSeriesList } from "../../seriesList.ts";

    // The games of the ended table's last series, newest first; a tap on a row opens its sheet as the live list does.
    // The route has an [id] segment, so the parameter is always present.
    const id = $derived(page.params.id as string);

    let sheet: HTMLDialogElement | undefined = $state();
    let rows = $state<GameRow[] | null>(null);
    let failed = $state(false);
    let opened = $state<GameRow | null>(null);

    $effect(() => {
        let current = true;
        void readSeriesList(id).then((entries) => {
            if (!current) return;
            failed = entries === null;
            rows = entries === null ? null : gameRows(entries);
        });
        return () => {
            current = false;
        };
    });
</script>

<div class="gamesbox">
    <span class="lbl">{words["table.seriesListTitle"]}</span>
    <ol class="rows">
        {#each rows ?? [] as row (row.number)}
            <li>
                <button
                    type="button"
                    class="grow"
                    onclick={() => {
                        opened = row;
                        sheet?.showModal();
                    }}
                >
                    <GameRowFace {row} />
                </button>
            </li>
        {/each}
    </ol>
    {#if failed}
        <p class="empty" role="alert">{words["table.seriesListFailed"]}</p>
    {/if}
</div>
<dialog
    bind:this={sheet}
    class="game-list"
    aria-label={words["table.seriesList"]}
    onclose={() => {
        opened = null;
    }}
    onclick={(event) => {
        if (event.target === sheet) sheet.close();
    }}
>
    {#if opened !== null}
        <GameSheet {id} row={opened} back={() => sheet?.close()} />
    {/if}
</dialog>
