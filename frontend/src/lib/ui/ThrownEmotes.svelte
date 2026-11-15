<script lang="ts">
    import { flyingEmotes } from "#lib/tableReactions.svelte.ts";
    import { words } from "#lib/words.ts";
    import { reactionMark, reactionName } from "../../routes/(start)/reaction.ts";
    import { drawingOrder, type Chair } from "../../routes/(start)/tables.ts";

    // An emote is thrown from the chair of whoever threw it, as the chairs are drawn, and lands on the felt; a watcher has
    // no chair and throws from the rim. Where it lands follows its number at the table, so emotes thrown together do not
    // lie on one another. The felt carries the picture; the sentence beside it says what was thrown, for a screen reader.
    const { chairs }: { chairs: Chair[] } = $props();

    // The stylesheet knows where an emote starts, by the chair's place in the drawing (the rim for a watcher), and the spots
    // it may land at.
    const SPOTS = 5;

    const placed = $derived(
        flyingEmotes().map((thrown) => {
            const place = drawingOrder(chairs).findIndex((chair) => chair.seat === thrown.by_seat);
            return { thrown, from: place < 0 ? "rim" : String(place), spot: String(thrown.number % SPOTS) };
        }),
    );
    const latest = $derived(flyingEmotes().at(-1));
</script>

<div class="thrown" aria-hidden="true">
    {#each placed as { thrown, from, spot } (thrown.number)}
        {@const mark = reactionMark(thrown.reaction)}
        <span class="emote" data-from={from} data-spot={spot}>
            {mark === null ? "" : words[mark]}
            {#if thrown.by_name !== null}<span class="from">{thrown.by_name.slice(0, 1)}</span>{/if}
        </span>
    {/each}
</div>
<p class="sr-only" role="status">
    {#if latest !== undefined}{latest.by_name ?? ""} {words[reactionName(latest.reaction)]}{/if}
</p>
