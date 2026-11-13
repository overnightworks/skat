<script lang="ts">
    import { ownCardSlotOpen, trickOnTheFelt } from "#lib/playView.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import { words } from "#lib/words.ts";
    import { cardName, includesCard, type Card, type Chair, type Playing } from "../../routes/(start)/tables.ts";

    // The cards this page saw played in the running hand; only those land, a card drawn from a reload stands still.
    // `turnSeat` is the seat whose card the table waits for, undefined while the hand waits for a sitter.
    const {
        chairs,
        playing,
        playedThisHand,
        turnSeat,
    }: { chairs: Chair[]; playing: Playing; playedThisHand: Card[]; turnSeat: number | null | undefined } = $props();

    const laid = $derived(trickOnTheFelt(chairs, playing));
</script>

<ul class="trick" aria-label={words["play.trick"]}>
    {#each laid as { card, seat, slot, name, initial } (`${card.suit}-${card.rank}`)}
        <li class={`laid ${slot}${includesCard(playedThisHand, card) ? " fresh" : ""}`} data-seat={seat}>
            <span class="face" role="img" aria-label={cardName(card)}><CardFace {card} /></span>
            <span class="tag">
                <span class="dot" aria-hidden="true">{initial}</span>
                <span class="name">{name}</span>
            </span>
        </li>
    {/each}
    {#if ownCardSlotOpen(chairs, laid, turnSeat)}
        <li class="lead-slot" aria-hidden="true">
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"
            >
                <path d="M12 19V5M6 11l6-6 6 6" />
            </svg>
        </li>
    {/if}
</ul>
