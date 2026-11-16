<script lang="ts">
    import { reactionTray, setReactionTray } from "#lib/tableReactions.svelte.ts";
    import { words } from "#lib/words.ts";
    import { REACTION_TRAY_ID } from "../../routes/(start)/reaction.ts";

    // The key in the table's top row that opens a phone's tray of emotes below it; a wide screen shows the tray always and
    // has no key. The top row's room is the only one a phone has left: the row of keys below is drawn to the last pixel.
    const DESKTOP_FROM = 900;
    const GAP_BELOW_THE_KEY = 8;
    let viewportWidth = $state(0);
</script>

<svelte:window
    bind:innerWidth={viewportWidth}
    onresize={() => {
        setReactionTray(false);
    }}
/>

{#if viewportWidth < DESKTOP_FROM}
    <button
        type="button"
        class="reaction-key"
        class:on={reactionTray().open}
        aria-expanded={reactionTray().open}
        aria-controls={REACTION_TRAY_ID}
        aria-label={words["table.reactions"]}
        title={words["table.reactions"]}
        onclick={(event) => {
            const below = event.currentTarget.getBoundingClientRect().bottom + GAP_BELOW_THE_KEY;
            setReactionTray(!reactionTray().open, below);
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
{/if}
