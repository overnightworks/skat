<script lang="ts">
    import { beatOf } from "#lib/tableReactions.svelte.ts";
    import { tableStyle } from "#lib/tableStyle.svelte.ts";
    import { words } from "#lib/words.ts";
    import { reactionName, throwReaction } from "../../routes/(start)/reaction.ts";

    // The green-shaded brass lamp that stands on the rim and lights the room: a tap on it is a reaction every page at the
    // table shows and hears. It stands at the rim's edge, clear of every card and key, and the stylesheet places it.
    const { id }: { id: string } = $props();
</script>

{#if tableStyle() === "klassik"}
    <button
        type="button"
        class="decor lamp"
        data-beat={beatOf("lamp")}
        aria-label={words[reactionName("lamp")]}
        onclick={() => {
            void throwReaction(id, "lamp");
        }}
    >
        <svg viewBox="0 0 48 64" focusable="false" aria-hidden="true">
            <ellipse cx="24" cy="59" rx="15" ry="3.6" fill="#8c6a2f" />
            <ellipse cx="24" cy="57.6" rx="13" ry="2.6" fill="#c9a464" />
            <path d="M22.5 29h3v28h-3z" fill="#b08a45" />
            <path d="M5 32C5 16 13 6 24 6s19 10 19 26z" fill="#2f5d46" />
            <path d="M9 30C10 18 15 11 22 9" fill="none" stroke="#6fae8c" stroke-width="2" stroke-linecap="round" />
            <ellipse cx="24" cy="32" rx="19" ry="3" fill="#ffd9a0" />
        </svg>
    </button>
{/if}
