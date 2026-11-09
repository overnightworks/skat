<script lang="ts">
    import { inDisplayOrder } from "#lib/handOrder.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import type { Card } from "../../routes/(start)/tables.ts";

    const { cards }: { cards: readonly Card[] } = $props();

    const ordered = $derived(inDisplayOrder(cards));
    const topRowSize = $derived(Math.ceil(ordered.length / 2));
    const rows = $derived([ordered.slice(0, topRowSize), ordered.slice(topRowSize)]);
</script>

<div class="open">
    {#each rows as row, index (index)}
        <div class="open-row">
            {#each row as card (`${card.suit}-${card.rank}`)}
                <div class="card">
                    <CardFace {card} />
                </div>
            {/each}
        </div>
    {/each}
</div>
