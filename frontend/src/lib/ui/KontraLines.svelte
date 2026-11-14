<script lang="ts">
    import { Marked } from "overnightworks-design";
    import { plaqueLine, type FirstCardWait } from "#lib/kontra.ts";
    import type { Kontra } from "../../routes/(start)/tables.ts";

    const { kontra, wait }: { kontra: Kontra | null; wait: FirstCardWait | null } = $props();

    const said = $derived(plaqueLine(kontra));
</script>

{#snippet factor({ text }: { text: string })}<b>{text}</b>{/snippet}

<!-- The lines Kontra adds under the game on the plaque: the last word with its factor, and whom the first card waits on. -->
{#if said !== null}
    <span class="game pushes"><Marked parts={said} marked={{ factor }} /></span>
{/if}
{#if wait !== null}
    <span class="game gives">
        {#each wait.initials as initial, index (index)}
            <span class="face" aria-hidden="true">{initial}</span>
        {/each}
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {wait.text} compiles to a `?? ""` branch no text can take -->
        {`${wait.text}`}
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    </span>
{/if}
