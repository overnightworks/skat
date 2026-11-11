<script lang="ts">
    import { trickOnTheFelt } from "#lib/playView.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import { words } from "#lib/words.ts";
    import { cardName, includesCard, type Card, type Chair, type Playing } from "../../routes/(start)/tables.ts";

    // The cards this page saw played in the running hand; only those land, a card drawn from a reload stands still.
    const { chairs, playing, playedThisHand }: { chairs: Chair[]; playing: Playing; playedThisHand: Card[] } = $props();

    const laid = $derived(trickOnTheFelt(chairs, playing));
</script>

<ul class="trick" aria-label={words.trick}>
    {#each laid as { card, seat, slot, name, initial } (`${card.suit}-${card.rank}`)}
        <li class={`laid ${slot}${includesCard(playedThisHand, card) ? " fresh" : ""}`} data-seat={seat}>
            <span class="face" role="img" aria-label={cardName(card)}><CardFace {card} /></span>
            <span class="tag">
                <span class="dot" aria-hidden="true">{initial}</span>
                <span class="name">{name}</span>
            </span>
        </li>
    {/each}
</ul>
