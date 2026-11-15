<script lang="ts">
    import { tableStyle } from "#lib/tableStyle.svelte.ts";
    import { runAmbience } from "#lib/tableSound.ts";

    // The ambience belongs to the table's style and has no picture: the sea of the beach bar, the murmur of the pub room.
    // This part only tells the sound engine which one the table wants. The engine alone decides whether it sounds, by the
    // device's volume, its mute, a hidden window and whether a tap has woken the sound.
    const wanted = $derived(tableStyle() === "strandbar" ? "sea" : "pub");

    $effect(() => {
        // The engine reads the device's settings inside this effect, so a change of the volume or the mute runs it again.
        runAmbience(wanted);
    });

    $effect(() => () => {
        runAmbience(undefined);
    });
</script>

<svelte:document
    onvisibilitychange={() => {
        runAmbience(wanted);
    }}
/>
