<script lang="ts">
    import { words } from "#lib/words.ts";
    import LobbyButton from "./LobbyButton.svelte";
    import SoundButton from "./SoundButton.svelte";
    import TableRules from "./TableRules.svelte";

    import type { Bock, Options } from "../../routes/(start)/tables.ts";

    // `live` is the table while it runs: its watchers, the rules it was opened with and its Bock games. In a call the
    // wordmark stands in for the link to the Lobby and the call's own strip carries the speaker.
    let {
        callMode,
        attention,
        connected,
        live,
    }: {
        callMode: boolean;
        attention: number;
        connected: boolean;
        live: { watchers: number; options: Options; bock: Bock | null } | null;
    } = $props();
</script>

<header class="bar">
    {#if callMode}
        <span class="wordmark" class:stale={!connected}>{words["app.name"]}</span>
    {:else}
        <LobbyButton {attention} />
    {/if}
    {#if live !== null}
        <TableRules options={live.options} bock={live.bock} />
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
