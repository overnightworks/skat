<script lang="ts">
    import { currentSettings } from "#lib/settings.svelte.ts";
    import { tableStyle } from "#lib/tableStyle.svelte.ts";
    import { runSea } from "#lib/tableSound.ts";

    // The sea belongs to the Strandbar style and has no picture: this part only keeps the sound engine told. It reads
    // the device's volume and mute, so a change of either re-tunes the sea, and a hidden window fades it out.
    let hidden = $state(false);

    $effect(() => {
        // Reading the volume here makes a change of it, or of the mute, run the sea's tuning again.
        const { muted, volume } = currentSettings();
        runSea(tableStyle() === "strandbar" && !hidden && !muted && volume > 0);
        return () => {
            runSea(false);
        };
    });
</script>

<svelte:document
    onvisibilitychange={() => {
        hidden = document.hidden;
    }}
/>
