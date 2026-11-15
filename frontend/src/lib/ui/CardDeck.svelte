<script lang="ts">
    import CardBack from "./CardBack.svelte";
</script>

<div class="deck">
    {#each [0, 1, 2, 3] as layer (layer)}
        <div class="deck-card">
            <CardBack />
        </div>
    {/each}
</div>
