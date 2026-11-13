<script lang="ts">
    import { resolve } from "$app/paths";
    import { words } from "#lib/words.ts";
    import { attentionMark } from "../../routes/(start)/tables.ts";

    /** The number of the person's other tables that wait for him. */
    const { attention }: { attention: number } = $props();
</script>

<a
    class="lobby"
    href={resolve("/(start)")}
    title={words["table.lobby"]}
    aria-label={attention === 0 ? words["table.lobby"] : words["table.lobbyWaiting"](attention)}
>
    <span class="lobby-face button-glass">
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M4 11.5 12 5l8 6.5" />
            <path d="M6.5 10v9h11v-9" />
        </svg>
        <span class="lobby-word">{words["table.lobby"]}</span>
        {#if attention > 0}
            <span class="lobby-badge" aria-hidden="true">{attentionMark(attention)}</span>
        {/if}
    </span>
</a>
