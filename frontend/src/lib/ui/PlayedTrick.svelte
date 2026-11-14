<script lang="ts">
    import { ownCardSlotOpen, type LaidCard } from "#lib/playView.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import { words } from "#lib/words.ts";
    import { cardName, includesCard, type Card, type Chair } from "../../routes/(start)/tables.ts";

    // The cards this page saw played in the running hand; only those land, a card drawn from a reload stands still.
    // `turnSeat` is the seat whose card the table waits for, undefined while the hand waits for a sitter or a trick
    // is on the move. `sweptTo` is the seat whose pile the trick glides to while it glides.
    const {
        chairs,
        laid,
        playedThisHand,
        turnSeat,
        sweptTo,
    }: {
        chairs: Chair[];
        laid: LaidCard[];
        playedThisHand: Card[];
        turnSeat: number | null | undefined;
        sweptTo: number | null;
    } = $props();

    // A name that fits its tag whole leaves the tags of the trick apart, as the scenes draw them. A name cut to the tag's
    // cap makes tags that reach each other, so the near tag then steps below the far ones. Whether a name is cut never
    // depends on the step, so the measure cannot flip back and forth.
    let trick: HTMLUListElement | undefined = $state();
    let stepped = $state(false);

    function aNameIsCut(list: HTMLElement): boolean {
        return [...list.querySelectorAll(".tag .name")].some((name) => name.scrollWidth > name.clientWidth);
    }

    $effect(() => {
        const list = trick;
        // Reading the laid cards makes the measure follow every card laid or taken.
        if (list === undefined || laid.length === 0) {
            stepped = false;
            return;
        }
        const measure = (): void => {
            stepped = aNameIsCut(list);
        };
        const observer = new ResizeObserver(measure);
        observer.observe(list);
        for (const tag of list.querySelectorAll(".tag")) observer.observe(tag);
        return () => {
            observer.disconnect();
        };
    });

    type Point = { x: number; y: number };
    const centreOf = (box: DOMRect): Point => ({ x: box.left + box.width / 2, y: box.top + box.height / 2 });
    const px = (pixels: number): string => `${pixels.toFixed(0)}px`;
    // Each card turns a little more than the one before it while the trick gathers.
    const GATHER_TURN_DEGREES = 5;
    // The trail is a curve of this many points, bowed away from the line between the middle and the pile.
    const TRAIL_POINTS = 10;
    const TRAIL_BOW = 30;
    let trail = $state("");

    // The trick glides to the pile of its taker: each card measures its own way from where it lies to the middle of the
    // trick and on to the pile, since the grid puts the pile wherever the chair stands.
    $effect(() => {
        const list = trick;
        const pile =
            sweptTo === null ? null : list?.closest(".stage")?.querySelector(`.pile[data-seat="${String(sweptTo)}"]`);
        if (list === undefined || !pile) {
            trail = "";
            return;
        }
        const origin = list.getBoundingClientRect();
        const middle = centreOf(origin);
        const target = centreOf(pile.getBoundingClientRect());
        const pileCard = pile.querySelector<HTMLElement>(".card");
        for (const [index, card] of [...list.querySelectorAll<HTMLElement>(".laid")].entries()) {
            const here = centreOf(card.getBoundingClientRect());
            card.style.setProperty("--gx", px(middle.x - here.x));
            card.style.setProperty("--gy", px(middle.y - here.y));
            card.style.setProperty("--gr", `${String((index - 1) * GATHER_TURN_DEGREES)}deg`);
            card.style.setProperty("--wx", px(target.x - here.x));
            card.style.setProperty("--wy", px(target.y - here.y));
            card.style.setProperty("--ps", String((pileCard?.offsetWidth ?? card.offsetWidth) / card.offsetWidth));
        }
        const from = { x: middle.x - origin.left, y: middle.y - origin.top };
        const to = { x: target.x - origin.left, y: target.y - origin.top };
        const bend = { x: (from.x + to.x) / 2 - TRAIL_BOW, y: Math.min(from.y, to.y) + TRAIL_BOW };
        const along = (t: number, start: number, control: number, end: number): string =>
            ((1 - t) ** 2 * start + 2 * (1 - t) * t * control + t ** 2 * end).toFixed(0);
        trail = Array.from({ length: TRAIL_POINTS }, (_, step) => {
            const t = 0.1 + step * 0.09;
            return `${along(t, from.x, bend.x, to.x)} ${along(t, from.y, bend.y, to.y)}`;
        }).join("L");
    });
</script>

<ul class="trick" class:stepped class:sweeping={sweptTo !== null} aria-label={words["play.trick"]} bind:this={trick}>
    {#each laid as { card, seat, slot, name, initial } (`${card.suit}-${card.rank}`)}
        <li class={`laid ${slot}${includesCard(playedThisHand, card) ? " fresh" : ""}`} data-seat={seat}>
            <span class="face" role="img" aria-label={cardName(card)}><CardFace {card} /></span>
            <span class="tag">
                <span class="dot" aria-hidden="true">{initial}</span>
                <span class="name">{name}</span>
            </span>
        </li>
    {/each}
    {#if trail !== ""}
        <li class="trail" aria-hidden="true">
            <svg width="1" height="1"><path d={`M${trail}`} /></svg>
        </li>
    {/if}
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
