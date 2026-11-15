<script lang="ts">
    import { words } from "#lib/words.ts";
    import { EMOTES, reactionMark, reactionName, throwReaction } from "../../routes/(start)/reaction.ts";

    // Anyone at the table, a watcher too, throws an emote from the tray. A phone opens the tray from its key and closes it
    // after a throw; a wide screen shows the tray as a rail at the edge, always. The stream brings every throw back to every
    // page, this one included, so the page shows an emote once, thrown from the chair it came from.
    const { id }: { id: string } = $props();
    const uid = $props.id();
    const trayId = `${uid}-tray`;
    let open = $state(false);
</script>

<button
    type="button"
    class="copy reaction-key"
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
<div id={trayId} class="tray" class:open role="group" aria-label={words["table.reactionTray"]}>
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
