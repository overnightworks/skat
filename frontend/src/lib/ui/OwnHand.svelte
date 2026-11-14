<script lang="ts">
    import { inDisplayOrder } from "#lib/handOrder.ts";
    import { cardLook, dragVerdict, type PlayingHand } from "#lib/playView.ts";
    import { mayPick } from "#lib/pushView.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import { words } from "#lib/words.ts";
    import { cardName, includesCard, type Card, type Picking } from "../../routes/(start)/tables.ts";

    const {
        cards,
        picking,
        playing,
    }: { cards: readonly Card[]; picking?: Picking | undefined; playing?: PlayingHand | undefined } = $props();

    const ordered = $derived(inDisplayOrder(cards));

    // A card pressed and moved follows the pointer; the click that ends a drag must not tap the card as well.
    // A card dropped past the threshold stays where it was dropped until the update arrives, or the play is refused.
    type Press = PointerEvent & { currentTarget: HTMLButtonElement };
    let drag = $state<{ card: Card; startX: number; startY: number } | null>(null);
    let dropped = $state<Card | null>(null);
    let clickEndsDrag = false;
    const raised = $derived(drag?.card ?? dropped);

    const slotOf = (event: Press): HTMLElement => event.currentTarget.parentElement as HTMLElement;
    const travelOf = (event: Press, held: { startX: number; startY: number }) => ({
        dx: event.clientX - held.startX,
        dy: event.clientY - held.startY,
    });

    function press(event: Press, card: Card): void {
        if (event.button !== 0 || !event.isPrimary) return;
        clickEndsDrag = false;
        event.currentTarget.setPointerCapture(event.pointerId);
        drag = { card, startX: event.clientX, startY: event.clientY };
    }

    function move(event: Press): void {
        if (drag === null || !event.isPrimary) return;
        const { dx, dy } = travelOf(event, drag);
        slotOf(event).style.setProperty("--drag-x", `${String(dx)}px`);
        slotOf(event).style.setProperty("--drag-y", `${String(dy)}px`);
    }

    function letGo(event: Press): { card: Card; dx: number; dy: number } | null {
        if (drag === null || !event.isPrimary) return null;
        const held = { card: drag.card, ...travelOf(event, drag) };
        drag = null;
        return held;
    }

    function putBack(slot: HTMLElement): void {
        slot.style.removeProperty("--drag-x");
        slot.style.removeProperty("--drag-y");
    }

    function cancel(event: Press): void {
        const slot = slotOf(event);
        if (letGo(event) !== null) putBack(slot);
    }

    async function release(event: Press, hand: PlayingHand): Promise<void> {
        const slot = slotOf(event);
        const held = letGo(event);
        if (held === null) return;
        const verdict = dragVerdict(held, event.currentTarget.offsetHeight);
        clickEndsDrag = verdict !== "tap";
        if (verdict !== "play") {
            putBack(slot);
            return;
        }
        dropped = held.card;
        if (await hand.play(held.card)) return;
        dropped = null;
        putBack(slot);
    }

    function tapUnlessDragged(hand: PlayingHand, card: Card): void {
        if (!clickEndsDrag) hand.tap(card);
        clickEndsDrag = false;
    }
</script>

<div class="own-hand" class:picking={picking !== undefined}>
    {#each ordered as card (`${card.suit}-${card.rank}`)}
        {@const look = cardLook(playing, card)}
        {@const pickable = picking === undefined || mayPick(picking, card)}
        <div
            class="card"
            class:ok={look === "legal"}
            class:touch={look === "lifted"}
            class:no={look === "dimmed" || !pickable}
            class:dragging={raised !== null && includesCard([raised], card)}
        >
            {#if picking !== undefined}
                <button
                    type="button"
                    class="pick"
                    class:picked={includesCard(picking.picked, card)}
                    aria-pressed={includesCard(picking.picked, card)}
                    aria-label={cardName(card)}
                    disabled={picking.disabled || !pickable}
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
                    onpointerdown={(event) => {
                        press(event, card);
                    }}
                    onpointermove={move}
                    onpointerup={(event) => {
                        void release(event, playing);
                    }}
                    onpointercancel={cancel}
                    onclick={() => {
                        tapUnlessDragged(playing, card);
                    }}
                >
                    <CardFace {card} />
                </button>
                {#if look === "lifted"}
                    <span class="swipe" role="img" aria-label={words["play.swipeHint"]}>
                        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
                    </span>
                {/if}
            {:else}
                <CardFace {card} />
            {/if}
        </div>
    {/each}
</div>
