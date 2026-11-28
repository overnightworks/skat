<script lang="ts">
    import { lookOf } from "#lib/looks/registry.ts";
    import type { PanelSide } from "#lib/panelPlace.ts";
    import { changeSetting, currentSettings } from "#lib/settings.svelte.ts";
    import { TABLE_STYLE_TOKENS } from "#lib/wire.ts";
    import { tableStyle } from "#lib/tableStyle.svelte.ts";
    import { words } from "#lib/words.ts";
    import { chooseStyle, type TableStyle } from "../../routes/(start)/tables.ts";
    import AnchoredPanel from "./AnchoredPanel.svelte";
    import PaletteMark from "./PaletteMark.svelte";
    import StylePreview from "./StylePreview.svelte";

    // The panel that gives the whole table its style, which a seated person opens from the table menu. The stream brings
    // the change to every page, this one included; until it does, the panel shows the choice, and a refusal gives the
    // table's style back. It hangs on `anchor`, the menu's key.
    let {
        id,
        note = $bindable(),
        anchor,
        side,
        open = $bindable(),
    }: { id: string; note: string; anchor: HTMLElement | undefined; side: PanelSide; open: boolean } = $props();
    const instanceId = $props.id();
    const labelId = `${instanceId}-style-label`;

    // The widths of the blessed pictures: a phone's panel and a desktop's, from the width the stylesheet shows the word at.
    const PHONE_PANEL_WIDTH = 328;
    const DESKTOP_PANEL_WIDTH = 360;
    const DESKTOP_FROM = 900;

    let viewportWidth = $state(0);
    let shown = $derived(tableStyle());

    async function choose(style: TableStyle): Promise<void> {
        note = "";
        shown = style;
        if ((await chooseStyle(id, crypto.randomUUID(), style)).kind === "table") return;
        shown = tableStyle();
        note = words["table.commandFailed"];
    }
</script>

<svelte:window bind:innerWidth={viewportWidth} />

<AnchoredPanel
    {anchor}
    bind:open
    {side}
    width={viewportWidth >= DESKTOP_FROM ? DESKTOP_PANEL_WIDTH : PHONE_PANEL_WIDTH}
    title={words["table.styleName"]}
>
    <div class="sound-head">
        <PaletteMark />
        {words["table.styleName"]}
    </div>
    <div class="style-body">
        <div class="style-row">
            <b class="style-label" id={labelId}>{words["table.style"]}</b>
            <div class="style-tiles" role="radiogroup" aria-labelledby={labelId}>
                {#each TABLE_STYLE_TOKENS as style (style)}
                    <label class="style-tile style-{style}">
                        <input
                            type="radio"
                            name="table-style"
                            checked={style === shown}
                            onchange={() => {
                                void choose(style);
                            }}
                        />
                        <span class="style-face">
                            <StylePreview {style} />
                            <span class="style-name">
                                {#if style === shown}
                                    <svg
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        stroke-width="2.8"
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        aria-hidden="true"
                                    >
                                        <path d="M5 12.5l4.5 4.5L19 7.5" />
                                    </svg>
                                {/if}
                                {words[lookOf(style).name]}
                            </span>
                        </span>
                    </label>
                {/each}
            </div>
        </div>
        <p class="sound-note style-note">{words["table.styleNote"]}</p>
        <!-- The look under construction shows on this device only, whatever the table's style. -->
        <label class="sound-row">
            <span class="sound-row-name">{words["table.newLook"]}</span>
            <input
                type="checkbox"
                role="switch"
                class="sound-switch"
                checked={currentSettings().newLook}
                onchange={(event) => {
                    changeSetting("newLook", event.currentTarget.checked);
                }}
            />
        </label>
    </div>
</AnchoredPanel>
