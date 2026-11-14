<script lang="ts">
    import { closeOnEscape } from "#lib/closeOnEscape.ts";
    import type { LaidCard } from "#lib/playView.ts";
    import { stopLooking } from "#lib/stage.svelte.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import { words } from "#lib/words.ts";
    import { cardName } from "../../routes/(start)/tables.ts";
    import type { Attachment } from "svelte/attachments";

    // The last trick lifted out of its pile, face up, in the order it was played; the card that took it wears the pile's
    // rim. A tap anywhere puts it back and plays nothing: the taps that make it are swallowed before they reach the page.
    const { cards, takerSeat }: { cards: LaidCard[]; takerSeat: number } = $props();

    // The caret stays this far from the dialog's rounded corners.
    const CARET_MARGIN = 24;
    const TAPS = ["pointerdown", "pointerup", "click"] as const;

    // A tap swallowed, then the click that ends it puts the trick back.
    function swallowTaps(): () => void {
        const swallow = (event: Event): void => {
            event.stopPropagation();
            event.preventDefault();
            if (event.type === "click") stopLooking();
        };
        for (const type of TAPS) window.addEventListener(type, swallow, { capture: true });
        return () => {
            for (const type of TAPS) window.removeEventListener(type, swallow, { capture: true });
        };
    }

    // The caret points at the pile the trick came from: down at one below the dialog, up at one above it.
    function hangOnPile(seat: number): Attachment<HTMLElement> {
        return (dialog) => {
            // The dialog is positioned, so it has an offset parent, and only the taker's pile can be tapped to open it.
            const stage = dialog.offsetParent as Element;
            const pile = document.querySelector(`.pile[data-seat="${String(seat)}"]`) as Element;
            const room = stage.getBoundingClientRect();
            const at = pile.getBoundingClientRect();
            const reach = dialog.offsetWidth / 2 - CARET_MARGIN;
            const offset = at.left + at.width / 2 - room.left - (dialog.offsetLeft + dialog.offsetWidth / 2);
            dialog.style.setProperty("--caret", `${String(Math.max(-reach, Math.min(reach, offset)))}px`);
            dialog.classList.toggle(
                "over",
                at.top + at.height / 2 - room.top < dialog.offsetTop + dialog.offsetHeight / 2,
            );
        };
    }
</script>

<div
    class="lastshow"
    role="dialog"
    aria-label={words["play.lastTrick"]}
    {@attach swallowTaps}
    {@attach hangOnPile(takerSeat)}
    {@attach closeOnEscape(stopLooking)}
>
    <div class="lt-head">{words["play.lastTrick"]}</div>
    <ul class="lt-cards">
        {#each cards as { card, seat, name, initial } (seat)}
            <li class="lt-card" class:took={seat === takerSeat}>
                <span class="face" role="img" aria-label={cardName(card)}><CardFace {card} /></span>
                <span class="tag">
                    <span class="dot" aria-hidden="true">{initial}</span>
                    <span class="name">{name}</span>
                </span>
            </li>
        {/each}
    </ul>
</div>
