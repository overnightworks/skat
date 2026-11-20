<script lang="ts">
    import CardFace from "#lib/ui/CardFace.svelte";
    import { words } from "#lib/words.ts";

    const JACK_SUITS = ["kreuz", "pik", "herz", "karo"] as const;

    const { stale }: { stale: boolean } = $props();
</script>

<div class="start-table" class:stale>
    <div class="lobby-chair start-chair" data-side="left"></div>
    <div class="lobby-chair start-chair" data-side="right"></div>
    <div class="lobby-table"><div class="lobby-felt"></div></div>
    <p class="start-lull" role="status">{words["lobby.nobodyPlays"]}</p>
    <div class="start-jacks" aria-hidden="true">
        {#each JACK_SUITS as suit (suit)}
            <span class="start-jack" data-suit={suit}><CardFace card={{ suit, rank: "jack" }} /></span>
        {/each}
    </div>
</div>
