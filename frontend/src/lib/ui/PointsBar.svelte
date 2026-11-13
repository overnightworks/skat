<script lang="ts">
    import type { SideNames } from "#lib/playView.ts";
    import { ALL_POINTS } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";

    import type { Sides } from "../../routes/(start)/tables.ts";

    let { sides, points }: { sides: SideNames; points: Sides } = $props();
</script>

<div class="points" role="group" aria-label={words["result.trickPoints"]}>
    <span class="sides">
        <span class="declarer"
            ><span class="side">{sides.declarer}</span> <span class="tally">{points.declarer}</span></span
        >
        <span class="opponents"
            ><span class="side">{sides.opponents}</span> <span class="tally">{points.opponents}</span></span
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
