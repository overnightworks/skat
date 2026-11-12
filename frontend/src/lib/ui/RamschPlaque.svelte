<script lang="ts">
    import type { RamschPlaque } from "#lib/ramschView.ts";
    import { words } from "#lib/words.ts";

    const { plaque }: { plaque: RamschPlaque } = $props();
</script>

<div class="plaque ramsch">
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    <span class="game">{`${words["table.ramsch"]}`}</span>
    {#if plaque.pushes !== null}
        <span class="game pushes">
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {plaque.pushes} compiles to a `?? ""` branch no line can take -->
            {`${plaque.pushes}`}
            {#if plaque.factor !== null}
                <b>{plaque.factor}</b>
            {/if}
        </span>
    {/if}
    {#if plaque.acting !== null}
        <span class="game">
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {plaque.acting} compiles to a `?? ""` branch no line can take -->
            {`${plaque.acting}`}
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </span>
    {/if}
    {#if plaque.waiting}
        <span class="game">
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
            {`${words["table.waitingForPlayers"]}`}
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </span>
    {/if}
</div>
