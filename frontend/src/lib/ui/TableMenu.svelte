<script lang="ts">
    import type { KitWords } from "overnightworks-design";
    import { abortView } from "#lib/abort.ts";
    import { giveUpOffered } from "#lib/giveUp.ts";
    import { seriesEndOffered } from "#lib/series.ts";
    import { words } from "#lib/words.ts";
    import AbortKey from "./AbortKey.svelte";
    import AgentsList from "./AgentsList.svelte";
    import AnchoredPanel from "./AnchoredPanel.svelte";
    import CloseQuestion from "./CloseQuestion.svelte";
    import CopyLinkKey from "./CopyLinkKey.svelte";
    import GiveUpKey from "./GiveUpKey.svelte";
    import SeriesEndKey from "./SeriesEndKey.svelte";
    import StandKey from "./StandKey.svelte";
    import PaletteMark from "./PaletteMark.svelte";
    import PowerMark from "./PowerMark.svelte";
    import StylePanel from "./StylePanel.svelte";

    import type { Table } from "../../routes/(start)/tables.ts";

    // Every matter of the table that is not the game's next decision lies behind this key. `bar` stands in the table's
    // top row and opens downwards; `strip` stands last in the bottom strip, where a call leaves the top row to the call,
    // and opens upwards. In a call the table has no link to share.
    let {
        id,
        table,
        note = $bindable(),
        place,
        callMode,
        seated,
        styleOffered,
        oncopy,
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
        onstand: () => void;
        streamedVersion: number | null;
        seatedAgents: string;
        watchers: number;
        kitWords: KitWords;
    } = $props();

    // The widths of the blessed pictures: a phone's menu and a desktop's, from the width the stylesheet widens the bar at.
    const PHONE_PANEL_WIDTH = 300;
    const DESKTOP_PANEL_WIDTH = 320;
    const DESKTOP_FROM = 900;

    let key: HTMLButtonElement | undefined = $state();
    let open = $state(false);
    let styleOpen = $state(false);
    let closeAsked = $state(false);
    let agentsShown = $state(false);
    let viewportWidth = $state(0);

    const side = $derived(place === "strip" ? "above" : "below");
    const standOffered = $derived(seated);
    const closeOffered = $derived(table.opened_by_me && !callMode);
    const tableRows = $derived(
        !callMode || agentsShown || styleOffered || standOffered || closeOffered || seriesEndOffered(table),
    );
    const gameRows = $derived(giveUpOffered(table) || abortView(table).offered);

    function close(): void {
        open = false;
    }
</script>

<svelte:window bind:innerWidth={viewportWidth} />

{#if tableRows || gameRows}
    <button
        bind:this={key}
        type="button"
        class={["menu-key", place === "strip" && "strip", open && "on"]}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={words["table.menu"]}
        title={words["table.menu"]}
        onclick={() => {
            open = true;
        }}
    >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" aria-hidden="true">
            {#if place === "strip"}
                <path d="M5 7h14M5 12h14M5 17h14" stroke-width="2.2" />
            {:else}
                <circle cx="5.5" cy="12" r="1.7" fill="currentColor" stroke="none" />
                <circle cx="12" cy="12" r="1.7" fill="currentColor" stroke="none" />
                <circle cx="18.5" cy="12" r="1.7" fill="currentColor" stroke="none" />
            {/if}
        </svg>
    </button>
{/if}
<AnchoredPanel
    anchor={key}
    bind:open
    {side}
    width={viewportWidth >= DESKTOP_FROM ? DESKTOP_PANEL_WIDTH : PHONE_PANEL_WIDTH}
    title={words["table.menu"]}
>
    <div class="menu">
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
            <AgentsList
                tableId={id}
                {streamedVersion}
                {seatedAgents}
                {watchers}
                {kitWords}
                {open}
                bind:shown={agentsShown}
            />
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
            <GiveUpKey {id} {table} bind:note onsent={close} />
            <AbortKey {id} {table} bind:note onsent={close} />
        {/if}
    </div>
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
