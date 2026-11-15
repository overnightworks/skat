<script lang="ts">
    import { words } from "#lib/words.ts";
    import { EMOTES, reactionMark, reactionName, throwReaction } from "../../routes/(start)/reaction.ts";

    // Anyone at the table, a watcher too, throws an emote from the tray. A phone opens the tray from its key and closes it
    // after a throw, standing above the row of keys, so that it covers none of them; a wide screen shows the tray as a rail
    // at the edge, always. The stream brings every throw back to every page, this one included, so the page shows an emote
    // once, thrown from the chair it came from.
    const { id }: { id: string } = $props();
    const uid = $props.id();
    const trayId = `${uid}-tray`;
    let open = $state(false);
    let key: HTMLButtonElement | undefined = $state();
    let tray: HTMLDivElement | undefined = $state();

    // The row of keys is where the key stands; the tray rests this far above its top edge, and the stylesheet reads where.
    const GAP_ABOVE_THE_KEYS = 8;

    function standAboveTheKeys(): void {
        const row = key?.parentElement;
        if (row === null || row === undefined || tray === undefined) return;
        const above = document.documentElement.clientHeight - row.getBoundingClientRect().top + GAP_ABOVE_THE_KEYS;
        tray.style.setProperty("--tray-bottom", `${String(above)}px`);
    }

    $effect(() => {
        if (open) standAboveTheKeys();
    });
</script>

<svelte:window
    onresize={() => {
        if (open) standAboveTheKeys();
    }}
/>

<button
    type="button"
    class="copy reaction-key"
    bind:this={key}
    class:on={open}
    aria-expanded={open}
    aria-controls={trayId}
    aria-label={words["table.reactions"]}
    title={words["table.reactions"]}
    onclick={() => {
        open = !open;
    }}
>
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <circle cx="12" cy="12" r="9" />
        <path d="M8.5 14.2a4.2 4.2 0 0 0 7 0" />
        <circle cx="9" cy="9.8" r="1" fill="currentColor" stroke="none" />
        <circle cx="15" cy="9.8" r="1" fill="currentColor" stroke="none" />
    </svg>
</button>
<div id={trayId} class="tray" class:open bind:this={tray} role="group" aria-label={words["table.reactionTray"]}>
    {#each EMOTES as reaction (reaction)}
        {@const mark = reactionMark(reaction)}
        <button
            type="button"
            aria-label={words[reactionName(reaction)]}
            title={words[reactionName(reaction)]}
            onclick={() => {
                open = false;
                void throwReaction(id, reaction);
            }}
        >
            {mark === null ? "" : words[mark]}
        </button>
    {/each}
</div>
