<script lang="ts">
    import { untrack } from "svelte";
    import type { Action } from "svelte/action";
    import type { Seal } from "#lib/closingHand.ts";
    import { ownCardSlotOpen, type LaidCard } from "#lib/playView.ts";
    import { motionOnStage } from "#lib/stage.svelte.ts";
    import { gatherTimeline, liftTimeline, takerTimeline } from "#lib/takt/gather.ts";
    import { carryOf, landTimeline, lieOf } from "#lib/takt/land.ts";
    import { letGoPlaceOf } from "#lib/takt/letGo.ts";
    import { fade, letRest, move, placeOf } from "#lib/takt/player.ts";
    import type { Place } from "#lib/takt/timeline.ts";
    import CardBack from "#lib/ui/CardBack.svelte";
    import CardFace from "#lib/ui/CardFace.svelte";
    import OutcomeSeal from "#lib/ui/OutcomeSeal.svelte";
    import { words } from "#lib/words.ts";
    import { cardName, includesCard, type Card, type Chair } from "../../routes/(start)/tables.ts";

    // The cards this page saw played in the running hand; only those land, a card drawn from a reload lies at once.
    // `seed` is the seed of the running game, from which every card draws its lie, its toss and its place in a heap.
    // `turnSeat` is the seat whose card the table waits for, undefined while the hand waits for a sitter or a trick
    // is on the move. `sweptTo` is the seat whose pile the trick glides to while it glides. `took` is the seat whose card
    // took the finished trick, once that trick has lain, and the seal that card carries when it decided a declared hand.
    const {
        chairs,
        laid,
        playedThisHand,
        seed,
        turnSeat,
        sweptTo,
        took = null,
    }: {
        chairs: Chair[];
        laid: LaidCard[];
        playedThisHand: Card[];
        seed: string;
        turnSeat: number | null | undefined;
        sweptTo: number | null;
        took?: { seat: number; seal: Seal | null } | null;
    } = $props();

    const placesOf = (selector: string): Place[] => [...document.querySelectorAll(selector)].map(placeOf);
    const partOf = (card: HTMLElement, part: string): HTMLElement => card.querySelector(`.${part}`) as HTMLElement;

    // A card leaves from where the own hand let it go, else from its player's open cards, else from the middle of the
    // own hand when the viewer's seat played it elsewhere, else from the player's fan, which hides its faces.
    function leavingOf(card: Card, seat: number): { from: Place | undefined; faceDown: boolean } {
        const chair = `.chair[data-seat="${String(seat)}"]`;
        const midOwnHand = (): Place | undefined => {
            if (!chairs.some((each) => each.is_mine && each.seat === seat)) return undefined;
            const held = placesOf(".own-hand .card");
            return held[Math.floor(held.length / 2)];
        };
        const shown = letGoPlaceOf(card) ?? placesOf(`${chair} .open .card`)[0] ?? midOwnHand();
        return { from: shown ?? placesOf(`${chair} .fan`)[0], faceDown: shown === undefined };
    }

    // A card rests off its slot by its own lie, which the stylesheet reads from the element, set as properties so no
    // style attribute carries it. A card this page saw played is thrown there once, when its element is made; while
    // the stage does not move it lies at once.
    const rests: Action<HTMLLIElement, { card: Card; seat: number }> = (element, { card, seat }) => {
        const lie = lieOf(seed, card);
        element.style.setProperty("--lie-x", String(lie.x));
        element.style.setProperty("--lie-y", String(lie.y));
        element.style.setProperty("--lie-turn", `${String(lie.turn)}deg`);
        const land = motionOnStage()?.land;
        const landing =
            land !== undefined && includesCard(playedThisHand, card)
                ? landTimeline(land, {
                      ...leavingOf(card, seat),
                      to: placeOf(partOf(element, "lying")),
                      carry: carryOf(seed, card, land),
                  })
                : undefined;
        if (landing === undefined) return;
        move(partOf(element, "face"), landing.tracks.card, landing.seconds);
        move(partOf(element, "shade"), landing.tracks.shade, landing.seconds);
        fade(partOf(element, "rear"), landing.tracks.rear, landing.seconds);
        fade(partOf(element, "tag"), landing.tracks.name, landing.seconds);
    };

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

    const HELD = { stays: true };

    // The card that took the trick lifts once the trick has lain and stands lifted, in its brass rim, until the trick
    // is gathered or the result rises; a seal is pressed onto it.
    function lift(seat: number): (() => void) | undefined {
        const set = motionOnStage()?.trick;
        const card = trick?.querySelector<HTMLElement>(`.laid[data-seat="${String(seat)}"]`);
        if (set === undefined || !card) return undefined;
        const { tracks, seconds } = liftTimeline(set, placeOf(partOf(card, "lying")));
        move(partOf(card, "face"), tracks.card, seconds, HELD);
        move(partOf(card, "shade"), tracks.shade, seconds, HELD);
        fade(partOf(card, "rim"), tracks.rim, seconds);
        const seal = card.querySelector(".seal");
        if (seal !== null) move(seal, tracks.seal, seconds);
        return () => {
            letRest(card);
        };
    }

    // The trick is gathered onto its taker's pile: Takt moves each card between where it lies, the middle of the trick
    // and the pile's top card, all as the page measures them, since the grid puts the pile wherever the chair stands.
    // The pile's top card appears as the trick becomes it, at once when the trick is taken away early, and the taker's
    // chair answers.
    function gather(seat: number): (() => void) | undefined {
        const set = motionOnStage()?.trick;
        const stage = trick?.closest(".stage");
        const top = stage?.querySelector(`.pile[data-seat="${String(seat)}"] .landing`);
        if (trick === undefined || set === undefined || !stage || !top) return undefined;
        const cards = [...trick.querySelectorAll<HTMLElement>(".laid")];
        const box = trick.getBoundingClientRect();
        const { tracks, seconds } = gatherTimeline(set, seed, {
            cards: cards.map((card, index) => ({
                card: (laid[index] as LaidCard).card,
                lies: placeOf(partOf(card, "lying")),
                takes: Number(card.dataset.seat) === seat,
            })),
            middle: { x: box.left + box.width / 2, y: box.top + box.height / 2 },
            pile: placeOf(top),
        });
        for (const [index, card] of cards.entries()) {
            const each = tracks.cards[index] as (typeof tracks.cards)[number];
            move(partOf(card, "face"), each.card, seconds, HELD);
            move(partOf(card, "shade"), each.shade, seconds, HELD);
            fade(partOf(card, "rear"), each.rear, seconds, HELD);
            fade(partOf(card, "tag"), each.name, seconds, HELD);
            for (const mark of card.querySelectorAll(".rim, .seal")) fade(mark, each.rim, seconds, HELD);
        }
        fade(top, tracks.pile, seconds);
        const tile = stage.querySelector(`.chair[data-seat="${String(seat)}"] .tile`);
        if (tile !== null) {
            const taker = takerTimeline(set);
            if (taker.tracks.hop !== null) move(tile, taker.tracks.hop, taker.seconds);
            fade(tile, taker.tracks.flash, taker.seconds, { pseudoElement: "::after" });
        }
        return () => {
            letRest(top);
        };
    }

    // A seat alone starts the lift and the gathering, so a table that arrives meanwhile starts neither again.
    const liftedSeat = $derived(took?.seat ?? null);
    $effect(() => {
        const seat = liftedSeat;
        if (seat !== null) return untrack(() => lift(seat));
    });
    $effect(() => {
        const seat = sweptTo;
        if (seat !== null) return untrack(() => gather(seat));
    });
</script>

<ul class="trick" class:stepped aria-label={words["play.trick"]} bind:this={trick}>
    {#each laid as { card, seat, slot, name, initial } (`${card.suit}-${card.rank}`)}
        <li class={["laid", slot, took?.seat === seat && "took"]} data-seat={seat} use:rests={{ card, seat }}>
            <span class="lying">
                <span class="shade"></span>
                <span class="face" role="img" aria-label={cardName(card)}>
                    <CardFace {card} /><span class="rear"><CardBack /></span>
                    {#if took?.seat === seat}
                        <span class="rim"></span>
                        {#if took.seal !== null}
                            <OutcomeSeal seal={took.seal} />
                        {/if}
                    {/if}
                </span>
            </span>
            <span class="hang">
                <span class="tag">
                    <span class="dot" aria-hidden="true">{initial}</span>
                    <span class="name">{name}</span>
                </span>
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
