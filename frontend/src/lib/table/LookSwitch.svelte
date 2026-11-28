<script lang="ts">
    import { changeSetting, currentSettings } from "#lib/settings.svelte.ts";
    import { words } from "#lib/words.ts";

    // The switch between today's surface and the look under construction, on this device only. A look stands it where a
    // person always finds it, so the way back is one tap.
</script>

<label class="look-switch">
    <span class="look-switch-name">{words["table.newLook"]}</span>
    <input
        type="checkbox"
        role="switch"
        checked={currentSettings().newLook}
        onchange={(event) => {
            changeSetting("newLook", event.currentTarget.checked);
        }}
    />
</label>
