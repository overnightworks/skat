<script lang="ts">
    import type { KitWords } from "overnightworks-design";
    import { abortView } from "#lib/abort.ts";
    import { giveUpOffered, playOpenKey, shortenKey } from "#lib/giveUp.ts";
    import { seriesEndOffered } from "#lib/series.ts";
    import { words } from "#lib/words.ts";
    import AbortKey from "./AbortKey.svelte";
    import AgentsList from "./AgentsList.svelte";
    import AgentsMark from "./AgentsMark.svelte";
    import AnchoredPanel from "./AnchoredPanel.svelte";
    import CloseQuestion from "./CloseQuestion.svelte";
    import CopyLinkKey from "./CopyLinkKey.svelte";
    import GiveUpKey from "./GiveUpKey.svelte";
    import MenuKey from "./MenuKey.svelte";
    import { menuPanelWidth } from "./menuWidth.ts";
    import PlayOpenKey from "./PlayOpenKey.svelte";
    import ShortenKey from "./ShortenKey.svelte";
    import SeriesEndKey from "./SeriesEndKey.svelte";
    import StandKey from "./StandKey.svelte";
    import PaletteMark from "./PaletteMark.svelte";
    import PowerMark from "./PowerMark.svelte";
    import StylePanel from "./StylePanel.svelte";

    import type { Table } from "../../routes/(start)/tables.ts";

    // Every matter of the table that is not the game's next decision lies behind the menu's key, above its account.
    // `strip` is the bottom strip, where a call leaves the top row to the call. In a call the table has no link to share.
    let {
        id,
        table,
        note = $bindable(),
        place,
        callMode,
        seated,
        styleOffered,
        oncopy,
        onrules,
        onstand,
        streamedVersion,
        seatedAgents,
        watchers,
        kitWords,
    }: {
        id: string;
        table: Table;
        note: string;
        place: "bar" | "strip";
        callMode: boolean;
        seated: boolean;
        styleOffered: boolean;
        oncopy: () => void;
        onrules: () => void;
        onstand: () => void;
        streamedVersion: number | null;
        seatedAgents: string;
        watchers: number;
        kitWords: KitWords;
    } = $props();

    let key: HTMLButtonElement | undefined = $state();
    let open = $state(false);
    let styleOpen = $state(false);
    let agentsOpen = $state(false);
    let closeAsked = $state(false);
    let agentsShown = $state(false);
    let viewportWidth = $state(0);

    const side = $derived(place === "strip" ? "above" : "below");
    const standOffered = $derived(seated);
    const closeOffered = $derived(table.opened_by_me && !callMode);
    const tableRows = $derived(
        !callMode || agentsShown || styleOffered || standOffered || closeOffered || seriesEndOffered(table),
    );
    const gameRows = $derived(
        shortenKey(table) || playOpenKey(table) || giveUpOffered(table) || abortView(table).offered,
    );

    function close(): void {
        open = false;
    }
</script>

<svelte:window bind:innerWidth={viewportWidth} />

<MenuKey {place} bind:open bind:key {kitWords}>
    {#if tableRows}
        <h3 class="menu-section">{words["table.menuTable"]}</h3>
        {#if !callMode}
            <CopyLinkKey
                oncopy={() => {
                    close();
                    oncopy();
                }}
            />
        {/if}
        {#if agentsShown}
            <button
                type="button"
                class="row agents"
                onclick={() => {
                    close();
                    agentsOpen = true;
                }}
            >
                <AgentsMark />
                <span class="label">{words["table.agents"]}</span>
            </button>
        {/if}
        {#if styleOffered}
            <button
                type="button"
                class="row style"
                onclick={() => {
                    close();
                    styleOpen = true;
                }}
            >
                <PaletteMark />
                <span class="label">{words["table.style"]}</span>
            </button>
        {/if}
        {#if !callMode}
            <button
                type="button"
                class="row rules"
                onclick={() => {
                    close();
                    onrules();
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
                    <path d="M9 6.5h11M9 12h11M9 17.5h11" />
                    <path d="M4 6.5h.01M4 12h.01M4 17.5h.01" />
                </svg>
                <span class="label">{words["rules.title"]}</span>
            </button>
        {/if}
        {#if standOffered}
            <StandKey
                handRuns={table.hand !== null}
                onstand={() => {
                    close();
                    onstand();
                }}
            />
        {/if}
        {#if closeOffered}
            <button
                type="button"
                class="row close"
                onclick={() => {
                    close();
                    closeAsked = true;
                }}
            >
                <PowerMark />
                <span class="label">{words["table.close"]}</span>
            </button>
        {/if}
        <SeriesEndKey {id} {table} bind:note onsent={close} />
    {/if}
    {#if gameRows}
        <h3 class="menu-section">{words["table.menuGame"]}</h3>
        <ShortenKey {id} {table} bind:note onsent={close} />
        <PlayOpenKey {id} {table} bind:note onsent={close} />
        <GiveUpKey {id} {table} bind:note onsent={close} />
        <AbortKey {id} {table} bind:note onsent={close} />
    {/if}
</MenuKey>
<!-- The list stays mounted while its panel is closed: whether the server shows it decides the menu's row. -->
<AnchoredPanel
    anchor={key}
    bind:open={agentsOpen}
    {side}
    width={menuPanelWidth(viewportWidth)}
    title={words["table.agents"]}
>
    <div class="sound-head">
        <AgentsMark />
        {words["table.agents"]}
    </div>
    <AgentsList
        tableId={id}
        {streamedVersion}
        {seatedAgents}
        {watchers}
        {kitWords}
        open={open || agentsOpen}
        bind:shown={agentsShown}
    />
</AnchoredPanel>
{#if styleOffered}
    <StylePanel {id} bind:note anchor={key} {side} bind:open={styleOpen} />
{/if}
{#if closeAsked}
    <CloseQuestion
        {id}
        bind:note
        onanswered={() => {
            closeAsked = false;
        }}
    />
{/if}
