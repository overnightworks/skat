<script lang="ts">
    import type { TableStyle } from "../../routes/(start)/tables.ts";
    import { showTableStyle, tableStyle } from "#lib/tableStyle.svelte.ts";
    import Ambience from "./Ambience.svelte";
    import StrandScene from "./StrandScene.svelte";

    // What stands behind the table in a style: the page hands over the style of the table it shows, and this part tells
    // every other part of the page (the card backs, the stylesheet's attribute) and draws the style's scene and sound.
    const { style }: { style: TableStyle | null } = $props();

    $effect(() => {
        showTableStyle(style);
        // The page-wide style is this table's: leaving the table hands it back.
        return () => showTableStyle(null);
    });
</script>

{#if tableStyle() === "strandbar"}
    <StrandScene />
{/if}
<!-- A table that has ended has no style and no ambience. -->
{#if style !== null}
    <Ambience />
{/if}
