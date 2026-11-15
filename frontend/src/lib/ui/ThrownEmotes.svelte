<script lang="ts">
    import type { Attachment } from "svelte/attachments";
    import { flyingEmotes } from "#lib/tableReactions.svelte.ts";
    import { words } from "#lib/words.ts";
    import { reactionMark, reactionName } from "../../routes/(start)/reaction.ts";
    import { drawingOrder, type Chair } from "../../routes/(start)/tables.ts";

    // An emote is thrown from the chair of whoever threw it, as the chairs are drawn, and lands on the felt; a watcher has
    // no chair and throws from the rim. Where it lands follows its number at the table, so emotes thrown together do not
    // lie on one another. A knock does not fly: its fist lands beside the thrower's chair, two rings spreading from it. The
    // felt carries the picture; the sentence beside it says what was thrown, for a screen reader.
    const { chairs }: { chairs: Chair[] } = $props();

    // Where an emote starts and where it lands, in percent of the felt: the first chair stands at the far left, the second at
    // the far right, the own chair at the near edge, and a watcher throws from beyond it. The stylesheet flies the emote
    // between the two points; the dashed trail is drawn along the same arc. A knock has one point, beside the chair.
    type Point = { x: number; y: number };
    const CHAIR_ORIGINS: readonly Point[] = [
        { x: 8, y: 2 },
        { x: 92, y: 2 },
        { x: 50, y: 96 },
    ];
    const RIM_ORIGIN: Point = { x: 50, y: 112 };
    const KNOCK_SPOTS: readonly Point[] = [
        { x: 20, y: 30 },
        { x: 80, y: 30 },
        { x: 50, y: 80 },
    ];
    const RIM_KNOCK_SPOT: Point = { x: 12, y: 86 };
    const SPOTS: readonly Point[] = [
        { x: 42, y: 50 },
        { x: 58, y: 54 },
        { x: 50, y: 42 },
        { x: 36, y: 58 },
        { x: 64, y: 44 },
    ];
    // The arc rises this far above the higher of its two ends, and its last stretch is what the trail shows.
    const ARC_LIFT = 8;
    const TRAIL_FROM = 0.72;
    const TRAIL_STEP = 0.04;
    const TRAIL_POINTS = 8;

    function curve(t: number, from: number, control: number, to: number): number {
        return (1 - t) ** 2 * from + 2 * (1 - t) * t * control + t ** 2 * to;
    }

    function trailOf(origin: Point, landing: Point): string {
        const control = { x: landing.x + (origin.x - landing.x) * 0.45, y: Math.min(landing.y, origin.y) - ARC_LIFT };
        return Array.from({ length: TRAIL_POINTS }, (_, index) => {
            const t = TRAIL_FROM + index * TRAIL_STEP;
            const point = `${curve(t, origin.x, control.x, landing.x).toFixed(1)} ${curve(t, origin.y, control.y, landing.y).toFixed(1)}`;
            return `${index === 0 ? "M" : "L"}${point}`;
        }).join("");
    }

    // The stylesheet reads the two points from the element, set as properties so no style attribute carries them.
    function flyBetween(origin: Point, landing: Point): Attachment<HTMLElement> {
        return (element) => {
            element.style.setProperty("--ox", String(origin.x));
            element.style.setProperty("--oy", String(origin.y));
            element.style.setProperty("--lx", String(landing.x));
            element.style.setProperty("--ly", String(landing.y));
        };
    }

    const placed = $derived(
        flyingEmotes().map((thrown) => {
            const place = drawingOrder(chairs).findIndex((chair) => chair.seat === thrown.by_seat);
            const knocked = thrown.reaction === "knock";
            const landing = knocked
                ? (KNOCK_SPOTS[place] ?? RIM_KNOCK_SPOT)
                : (SPOTS[thrown.number % SPOTS.length] as Point);
            const origin = knocked ? landing : (CHAIR_ORIGINS[place] ?? RIM_ORIGIN);
            return { thrown, origin, landing, knocked, trail: knocked ? null : trailOf(origin, landing) };
        }),
    );
    const latest = $derived(flyingEmotes().at(-1));
</script>

<div class="thrown" aria-hidden="true">
    {#each placed as { thrown, origin, landing, knocked, trail } (thrown.number)}
        {@const mark = reactionMark(thrown.reaction)}
        {#if trail !== null}
            <svg class="emote-trail" viewBox="0 0 100 100" preserveAspectRatio="none"><path d={trail} /></svg>
        {/if}
        {#if knocked}<span class="knock-ring" {@attach flyBetween(origin, landing)}></span>{/if}
        <span class={["emote", { knocked }]} {@attach flyBetween(origin, landing)}>
            {mark === null ? "" : words[mark]}
            {#if thrown.by_name !== null}<span class={["from", `seat-${String(thrown.by_seat)}`]}
                    >{thrown.by_name.slice(0, 1)}</span
                >{/if}
        </span>
    {/each}
</div>
<p class="sr-only" role="status">
    {#if latest !== undefined}{latest.by_name ?? ""} {words[reactionName(latest.reaction)]}{/if}
</p>
