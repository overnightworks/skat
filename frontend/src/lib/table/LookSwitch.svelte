<script lang="ts">
    import { changeSetting, currentSettings } from "#lib/settings.svelte.ts";
    import { words } from "#lib/words.ts";

    // The switch between today's surface and the look under construction, on this device only. A look stands it where a
    // person always finds it, so the way back is one tap; a panel of today's surface names its own rows' classes.
    const {
        rowClass = "look-switch",
        nameClass = "look-switch-name",
        switchClass,
    }: { rowClass?: string; nameClass?: string; switchClass?: string } = $props();
</script>

<label class={rowClass}>
    <span class={nameClass}>{words["table.newLook"]}</span>
    <input
        type="checkbox"
        role="switch"
        class={switchClass}
        checked={currentSettings().newLook}
        onchange={(event) => {
            changeSetting("newLook", event.currentTarget.checked);
        }}
    />
</label>
