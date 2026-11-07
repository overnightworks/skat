<script lang="ts">
    import "overnightworks-appkit/appkit.css";
    import "#lib/start.css";
    import type { Snippet } from "svelte";

    let { children }: { children: Snippet } = $props();
</script>

{@render children()}
