<script lang="ts">
    import { TABLE_STYLE_TOKENS } from "#lib/wire.ts";
    import { tableStyle } from "#lib/tableStyle.svelte.ts";
    import { words } from "#lib/words.ts";
    import { chooseStyle, type TableStyle } from "../../routes/(start)/tables.ts";
    import AnchoredPanel from "./AnchoredPanel.svelte";

    // A seated person's key: it opens the panel that gives the whole table its style. The stream brings the change to
    // every page, this one included, so the panel shows what the table has and nothing it only asked for.
    let { id, note = $bindable() }: { id: string; note: string } = $props();

    // The widths of the blessed pictures: a phone's panel and a desktop's, from the width the stylesheet shows the word at.
    const PHONE_PANEL_WIDTH = 328;
    const DESKTOP_PANEL_WIDTH = 360;
    const DESKTOP_FROM = 900;

    const NAMES: Record<TableStyle, "table.styleKlassik" | "table.styleStrandbar"> = {
        klassik: "table.styleKlassik",
        strandbar: "table.styleStrandbar",
    };

    let button: HTMLButtonElement | undefined = $state();
    let open = $state(false);
    let viewportWidth = $state(0);
    const picked = $derived(tableStyle());

    async function choose(style: TableStyle): Promise<void> {
        note = "";
        if (style === picked) return;
        if ((await chooseStyle(id, crypto.randomUUID(), style)).kind !== "table") note = words["table.commandFailed"];
    }
</script>

<svelte:window bind:innerWidth={viewportWidth} />

{#snippet palette()}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path
            d="M12 3.5a8.5 8.5 0 1 0 0 17c1.4 0 2-1 1.5-2.1-.5-1.2.2-2.4 1.6-2.4H17a3.5 3.5 0 0 0 3.5-3.5C20.5 6.9 16.7 3.5 12 3.5z"
        />
        <circle cx="7.8" cy="11.2" r="1" fill="currentColor" stroke="none" />
        <circle cx="10.6" cy="7.6" r="1" fill="currentColor" stroke="none" />
        <circle cx="15" cy="7.9" r="1" fill="currentColor" stroke="none" />
    </svg>
{/snippet}

<button
    bind:this={button}
    type="button"
    class="copy style-key"
    class:on={open}
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-label={words["table.styleName"]}
    title={words["table.styleName"]}
    onclick={() => {
        open = true;
    }}
>
    {@render palette()}
    <span class="word">{words["table.style"]}</span>
</button>
<AnchoredPanel
    anchor={button}
    bind:open
    side="above"
    width={viewportWidth >= DESKTOP_FROM ? DESKTOP_PANEL_WIDTH : PHONE_PANEL_WIDTH}
    title={words["table.styleName"]}
>
    <div class="sound-head">
        {@render palette()}
        {words["table.styleName"]}
    </div>
    <div class="style-body">
        <div class="style-tiles" role="radiogroup" aria-label={words["table.styleName"]}>
            {#each TABLE_STYLE_TOKENS as style (style)}
                <label class="style-tile style-{style}">
                    <input
                        type="radio"
                        name="table-style"
                        checked={style === picked}
                        onchange={() => {
                            void choose(style);
                        }}
                    />
                    <span class="style-face">
                        <span class="style-preview" aria-hidden="true"></span>
                        <span class="style-name">
                            {#if style === picked}
                                <svg
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    stroke-width="2.8"
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                    aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg
                                >
                            {/if}
                            {words[NAMES[style]]}
                        </span>
                    </span>
                </label>
            {/each}
        </div>
        <p class="sound-note">{words["table.styleNote"]}</p>
    </div>
</AnchoredPanel>
