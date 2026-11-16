<script lang="ts">
    import "overnightworks-design/design.css";
    import "#lib/start.css";
    import "#lib/strand.css";
    import "#lib/reactions.css";
    import type { Snippet } from "svelte";

    let { children }: { children: Snippet } = $props();
</script>

{@render children()}
