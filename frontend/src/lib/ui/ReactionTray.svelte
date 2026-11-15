<script lang="ts">
    import { reactionTray, setReactionTray } from "#lib/tableReactions.svelte.ts";
    import { words } from "#lib/words.ts";
    import {
        EMOTES,
        REACTION_TRAY_ID,
        reactionMark,
        reactionName,
        throwReaction,
    } from "../../routes/(start)/reaction.ts";

    // Anyone at the table, a watcher too, throws an emote from the tray. A phone opens the tray from its key in the top row
    // and closes it after a throw, hanging below the key; a wide screen shows the tray as a rail at the edge, always. The
    // stream brings every throw back to every page, this one included, so the page shows an emote once, thrown from the
    // chair it came from.
    const { id }: { id: string } = $props();
    let tray: HTMLDivElement | undefined = $state();

    // The stylesheet reads where the tray hangs.
    $effect(() => {
        tray?.style.setProperty("--tray-top", `${String(reactionTray().top)}px`);
    });
</script>

<div
    id={REACTION_TRAY_ID}
    class="tray"
    class:open={reactionTray().open}
    bind:this={tray}
    role="group"
    aria-label={words["table.reactionTray"]}
>
    {#each EMOTES as reaction (reaction)}
        {@const mark = reactionMark(reaction)}
        <button
            type="button"
            aria-label={words[reactionName(reaction)]}
            title={words[reactionName(reaction)]}
            onclick={() => {
                setReactionTray(false);
                void throwReaction(id, reaction);
            }}
        >
            {mark === null ? "" : words[mark]}
        </button>
    {/each}
</div>
