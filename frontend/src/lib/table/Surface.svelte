<script lang="ts">
    import { lookUnderConstruction } from "#lib/looks/registry.ts";
    import { tapCounts } from "#lib/tableReactions.svelte.ts";
    import type { Table } from "../../routes/(start)/tables.ts";
    import Announcement from "./Announcement.svelte";
    import { tableIntents } from "./intents.ts";
    import { surfaceScene } from "./scene.ts";
    import { seatNote } from "./seatNote.svelte.ts";

    // A running table on a look that draws the whole surface: the scene and the intents come from the page's table, the
    // look draws them, and what the table says aloud is said here, never by a look.
    const { id, table }: { id: string; table: Table } = $props();

    const look = lookUnderConstruction;
    const scene = $derived(surfaceScene(table, tapCounts(), seatNote()?.text ?? null));
    const intents = $derived(tableIntents(id));
</script>

<look.renderer {look} {scene} {intents} />
<Announcement text={scene.notice} />
