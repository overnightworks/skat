<script lang="ts">
    import type { TableStyle } from "../../routes/(start)/tables.ts";
    import { showTableStyle, tableStyle } from "#lib/tableStyle.svelte.ts";
    import Sea from "./Sea.svelte";
    import StrandScene from "./StrandScene.svelte";

    // What stands behind the table in a style: the page hands over the style of the table it shows, and this part tells
    // every other part of the page (the card backs, the stylesheet's attribute) and draws the style's scene and sound.
    const { style }: { style: TableStyle | null } = $props();

    $effect(() => {
        showTableStyle(style);
    });
</script>

{#if tableStyle() === "strandbar"}
    <StrandScene />
{/if}
<Sea />
