<script lang="ts">
    import "overnightworks-design/design.css";
    import "#lib/start.css";
    import "#lib/looks/klassik.css";
    import "#lib/looks/strandbar.css";
    import "#lib/reactions.css";
    import type { Snippet } from "svelte";

    let { children }: { children: Snippet } = $props();
</script>

{@render children()}
