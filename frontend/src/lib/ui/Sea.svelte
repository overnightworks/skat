<script lang="ts">
    import { tableStyle } from "#lib/tableStyle.svelte.ts";
    import { runSea } from "#lib/tableSound.ts";

    // The sea belongs to the Strandbar style and has no picture: this part only tells the sound engine whether the
    // table wants it. The engine alone decides whether it sounds, by the device's volume, its mute and a hidden window.
    const wanted = $derived(tableStyle() === "strandbar");

    $effect(() => {
        // The engine reads the device's settings inside this effect, so a change of the volume or the mute runs it again.
        runSea(wanted);
    });

    $effect(() => () => {
        runSea(false);
    });
</script>

<svelte:document
    onvisibilitychange={() => {
        runSea(wanted);
    }}
/>
