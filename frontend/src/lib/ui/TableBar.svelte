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

    type Live = {
        id: string;
        version: number;
        watchers: number;
        options: Options;
        bock: Bock | null;
        count: string | null;
    };

    // `live` is the table while it runs: its watchers, the rules it was opened with, its Bock games and the series' count,
    // whose list reads again at each version of table `id`. `menu` is the table's menu, which stands at the bar's end. In a
    // call the wordmark stands in for the link to the Lobby, and the call's own strip carries the speaker and the menu of
    // a running table; a table that does not run has no strip, so the bar carries its menu. Once the call has greeted, the
    // bar's row is gone: the reaction key and tray stay, and the rules and the series list open from the table's menu.
    let {
        callMode,
        greeted,
        attention,
        connected,
        live,
        menu,
        rulesOpen = $bindable(false),
        seriesOpen = $bindable(false),
    }: {
        callMode: boolean;
        greeted: boolean;
        attention: number;
        menu: Snippet;
        rulesOpen?: boolean;
        seriesOpen?: boolean;
        connected: boolean;
        live: Live | null;
    } = $props();
</script>

{#snippet sheets(running: Live)}
    {#if running.count !== null}
        <SeriesCount
            id={running.id}
            text={running.count}
            version={running.version}
            key={!greeted}
            bind:open={seriesOpen}
        />
    {/if}
    <TableRules options={running.options} bock={running.bock} chips={!greeted} bind:open={rulesOpen} />
{/snippet}

{#if greeted}
    {#if live !== null}
        <div class="greeted-keys">
            <ReactionKey />
            <ReactionTray id={live.id} />
        </div>
        {@render sheets(live)}
    {/if}
{:else}
    <header class="bar">
        {#if callMode}
            <span class="wordmark" class:stale={!connected}>{words["app.name"]}</span>
        {:else}
            <LobbyButton {attention} />
        {/if}
        {#if live !== null}
            {@render sheets(live)}
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
{/if}
