<script lang="ts">
    import { words } from "#lib/words.ts";

    const PIPS = [
        { suit: "kreuz", fill: "#17191c" },
        { suit: "pik", fill: "#14873f" },
        { suit: "herz", fill: "#d81f35" },
        { suit: "karo", fill: "#ec9800" },
    ] as const;
</script>

<div class="start-mark">
    <b class="start-wordmark">{words["app.name"]}</b>
    <span class="start-pips" aria-hidden="true">
        {#each PIPS as { suit, fill } (suit)}
            <span><svg viewBox="0 0 100 100" {fill}><use href="#suit-{suit}" /></svg></span>
        {/each}
    </span>
</div>
