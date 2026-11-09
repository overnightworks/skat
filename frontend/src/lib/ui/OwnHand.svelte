<script lang="ts">
    import { inDisplayOrder } from "#lib/handOrder.ts";
    import { cardLook, type PlayingHand } from "#lib/playView.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import { cardName, includesCard, type Card, type Picking } from "../../routes/(start)/tables.ts";

    const {
        cards,
        picking,
        playing,
    }: { cards: readonly Card[]; picking?: Picking | undefined; playing?: PlayingHand | undefined } = $props();

    const ordered = $derived(inDisplayOrder(cards));
</script>

<div class="own-hand" class:picking={picking !== undefined}>
    {#each ordered as card (`${card.suit}-${card.rank}`)}
        {@const look = cardLook(playing, card)}
        <div class="card" class:ok={look === "legal"} class:touch={look === "lifted"} class:no={look === "dimmed"}>
            {#if picking !== undefined}
                <button
                    type="button"
                    class="pick"
                    class:picked={includesCard(picking.picked, card)}
                    aria-pressed={includesCard(picking.picked, card)}
                    aria-label={cardName(card)}
                    disabled={picking.disabled}
                    onclick={() => {
                        picking.toggle(card);
                    }}
                >
                    <CardFace {card} />
                </button>
            {:else if playing !== undefined && (look === "legal" || look === "lifted")}
                <button
                    type="button"
                    class="play"
                    aria-pressed={look === "lifted"}
                    aria-label={cardName(card)}
                    disabled={playing.disabled}
                    onclick={() => {
                        playing.tap(card);
                    }}
                >
                    <CardFace {card} />
                </button>
            {:else}
                <CardFace {card} />
            {/if}
        </div>
    {/each}
</div>
