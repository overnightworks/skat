<script lang="ts">
    import type { TableIntents } from "#lib/table/intents.ts";
    import { objectName, type TableScene } from "#lib/table/scene.ts";
    import type { LookEntry } from "../look.ts";

    // The flat table: every furnishing of the look stands on the felt, in the order the look lists it, and the stylesheet
    // places it at the rim's edge, clear of every card and key.
    const { look, scene, intents }: { look: LookEntry; scene: TableScene; intents: TableIntents } = $props();
</script>

{#each look.furniture as furnishing (furnishing.object)}
    <furnishing.Piece
        taps={scene.taps[furnishing.object] ?? 0}
        label={objectName(furnishing.object)}
        ontap={() => {
            intents.tap(furnishing.object);
        }}
    />
{/each}
