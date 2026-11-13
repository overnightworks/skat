<script lang="ts">
    import { Marked } from "overnightworks-design";

    import type { SideNames } from "#lib/playView.ts";
    import { ALL_POINTS } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";

    import type { Sides } from "../../routes/(start)/tables.ts";

    let { sides, points }: { sides: SideNames; points: Sides } = $props();
</script>

{#snippet side({ text }: { text: string })}<span class="side">{text}</span>{/snippet}
{#snippet tally({ text }: { text: string })}<span class="tally">{text}</span>{/snippet}

<div class="points" role="group" aria-label={words["result.trickPoints"]}>
    <span class="sides">
        <span class="declarer"
            ><Marked
                parts={words["result.sidePoints"]({ side: sides.declarer, points: String(points.declarer) })}
                marked={{ side, tally }}
            /></span
        >
        <span class="opponents"
            ><Marked
                parts={words["result.sidePoints"]({ side: sides.opponents, points: String(points.opponents) })}
                marked={{ side, tally }}
            /></span
        >
    </span>
    <span class="track">
        <svg viewBox={`0 0 ${String(ALL_POINTS)} 1`} preserveAspectRatio="none" aria-hidden="true">
            <rect class="declarer" width={points.declarer} height="1" />
            <rect class="opponents" x={ALL_POINTS - points.opponents} width={points.opponents} height="1" />
        </svg>
        <i class="win-line"></i>
    </span>
</div>
