<script lang="ts">
    import { resolve } from "$app/paths";
    import { words } from "#lib/words.ts";
    import SoundButton from "./SoundButton.svelte";
    import TableRules from "./TableRules.svelte";

    import type { Options } from "../../routes/(start)/tables.ts";

    // `live` is the table while it runs: its watchers and the rules it was opened with. In a call the wordmark stands
    // in for the link to the Lobby and the call's own strip carries the speaker.
    let {
        callMode,
        connected,
        live,
    }: { callMode: boolean; connected: boolean; live: { watchers: number; options: Options } | null } = $props();
</script>

<header class="bar">
    {#if callMode}
        <span class="wordmark" class:stale={!connected}>{words["app.name"]}</span>
    {:else}
        <a class="lobby" href={resolve("/(start)")} title={words["table.lobby"]} aria-label={words["table.lobby"]}>
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
            </span>
        </a>
    {/if}
    {#if live !== null}
        <TableRules options={live.options} />
        {#if !callMode}
            <SoundButton place="bar" />
        {/if}
        <div
            class="watchers"
            class:stale={!connected}
            title={words["table.watchers"]}
            role="group"
            aria-label={words["table.watchers"]}
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
                <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
                <circle cx="12" cy="12" r="3" />
            </svg>
            <span>{live.watchers}</span>
        </div>
    {/if}
</header>
