<script lang="ts">
    import "overnightworks-appkit/appkit.css";
    import type { Snippet } from "svelte";

    let { children }: { children: Snippet } = $props();
</script>

{@render children()}

<style>
    :global(body) {
        margin: 0;
    }
</style>
