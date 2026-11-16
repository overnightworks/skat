<script lang="ts">
    import type { Attachment } from "svelte/attachments";
    import { flyingEmotes } from "#lib/tableReactions.svelte.ts";
    import { flightOf, type Point } from "../../routes/(start)/flight.ts";
    import { emoteGlyph, spokenOf } from "../../routes/(start)/reaction.ts";
    import type { Chair } from "../../routes/(start)/tables.ts";

    // An emote is thrown from the chair of whoever threw it, as the chairs are drawn, and lands on the felt; a watcher has
    // no chair and throws from the rim. Where it lands follows its number at the table, so emotes thrown together do not
    // lie on one another. A knock does not fly: its fist lands beside the thrower's chair, two rings spreading from it. The
    // felt carries the picture; the sentence beside it says what was thrown, for a screen reader.
    const { chairs }: { chairs: Chair[] } = $props();

    // The stylesheet reads the two points from the element, set as properties so no style attribute carries them.
    function flyBetween(origin: Point, landing: Point): Attachment<HTMLElement> {
        return (element) => {
            element.style.setProperty("--ox", String(origin.x));
            element.style.setProperty("--oy", String(origin.y));
            element.style.setProperty("--lx", String(landing.x));
            element.style.setProperty("--ly", String(landing.y));
        };
    }

    const placed = $derived(flyingEmotes().map((thrown) => ({ thrown, ...flightOf(thrown, chairs) })));
    const spoken = $derived(spokenOf(flyingEmotes().at(-1)));
</script>

<div class="thrown" aria-hidden="true">
    {#each placed as { thrown, origin, landing, knocked, trail } (thrown.number)}
        {#if trail !== null}
            <svg class="emote-trail" viewBox="0 0 100 100" preserveAspectRatio="none"><path d={trail} /></svg>
        {/if}
        {#if knocked}<span class="knock-ring" {@attach flyBetween(origin, landing)}></span>{/if}
        <span class={["emote", { knocked }]} {@attach flyBetween(origin, landing)}>
            <span>{emoteGlyph(thrown.reaction)}</span>
            {#if thrown.by_name !== null}<span class={["from", `seat-${String(thrown.by_seat)}`]}
                    >{thrown.by_name.slice(0, 1)}</span
                >{/if}
        </span>
    {/each}
</div>
<p class="sr-only" aria-live="polite">{spoken}</p>
