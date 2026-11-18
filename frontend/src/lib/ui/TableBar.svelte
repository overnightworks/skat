<script lang="ts">
    import { words } from "#lib/words.ts";
    import type { Snippet } from "svelte";
    import LobbyButton from "./LobbyButton.svelte";
    import ReactionKey from "./ReactionKey.svelte";
    import ReactionTray from "./ReactionTray.svelte";
    import SeriesCount from "./SeriesCount.svelte";
    import SoundButton from "./SoundButton.svelte";
    import TableRules from "./TableRules.svelte";

    import type { Bock, Options } from "../../routes/(start)/tables.ts";

    // `live` is the table while it runs: its watchers, the rules it was opened with, its Bock games and the series' count,
    // whose list reads again at each version of table `id`. `menu` is the table's menu, which stands at the bar's end. In a
    // call the wordmark stands in for the link to the Lobby, and the call's own strip carries the speaker and the menu of
    // a running table; a table that does not run has no strip, so the bar carries its menu.
    let {
        callMode,
        attention,
        connected,
        live,
        menu,
        rulesOpen = $bindable(false),
    }: {
        callMode: boolean;
        attention: number;
        menu: Snippet;
        rulesOpen?: boolean;
        connected: boolean;
        live: {
            id: string;
            version: number;
            watchers: number;
            options: Options;
            bock: Bock | null;
            count: string | null;
        } | null;
    } = $props();
</script>

<header class="bar">
    {#if callMode}
        <span class="wordmark" class:stale={!connected}>{words["app.name"]}</span>
    {:else}
        <LobbyButton {attention} />
    {/if}
    {#if live !== null}
        {#if live.count !== null}
            <SeriesCount id={live.id} text={live.count} version={live.version} />
        {/if}
        <TableRules options={live.options} bock={live.bock} bind:open={rulesOpen} />
        <ReactionKey />
        <ReactionTray id={live.id} />
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
        {#if !callMode}
            {@render menu()}
        {/if}
    {:else}
        {@render menu()}
    {/if}
</header>
