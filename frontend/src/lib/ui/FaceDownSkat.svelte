<script lang="ts">
    import CardBack from "./CardBack.svelte";

    let { count }: { count: number } = $props();

    const cards = $derived(Array.from({ length: count }, (_, index) => index));
</script>

<div class="skat">
    {#each cards as card (card)}
        <div class="skat-card deal">
            <CardBack />
        </div>
    {/each}
</div>
