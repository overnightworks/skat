<script lang="ts">
    import { trickOnTheFelt } from "#lib/playView.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import { words } from "#lib/words.ts";
    import { cardName, includesCard, type Card, type Chair, type Playing } from "../../routes/(start)/tables.ts";

    // The cards this page saw played in the running hand; only those land, a card drawn from a reload stands still.
    const { chairs, playing, playedThisHand }: { chairs: Chair[]; playing: Playing; playedThisHand: Card[] } = $props();

    const laid = $derived(trickOnTheFelt(chairs, playing));

    // The near tag stands as low under its card as the far tags do, and steps below them only where its width reaches
    // one of theirs. Its width never depends on the step, so the measure cannot flip back and forth.
    let trick: HTMLUListElement | undefined = $state();
    let stepped = $state(false);

    function nearTagReachesAFarTag(list: HTMLElement): boolean {
        const near = list.querySelector(".laid.near .tag")?.getBoundingClientRect();
        if (near === undefined) return false;
        return [...list.querySelectorAll(".laid:not(.near) .tag")].some((tag) => {
            const far = tag.getBoundingClientRect();
            return near.left < far.right && far.left < near.right;
        });
    }

    $effect(() => {
        const list = trick;
        // Reading the laid cards makes the measure follow every card laid or taken.
        if (list === undefined || laid.length === 0) {
            stepped = false;
            return;
        }
        const measure = (): void => {
            stepped = nearTagReachesAFarTag(list);
        };
        const observer = new ResizeObserver(measure);
        observer.observe(list);
        for (const tag of list.querySelectorAll(".tag")) observer.observe(tag);
        return () => {
            observer.disconnect();
        };
    });
</script>

<ul class="trick" class:stepped aria-label={words["play.trick"]} bind:this={trick}>
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
