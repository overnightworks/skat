<script lang="ts">
    import type { KitWords } from "overnightworks-design";
    import type { Snippet } from "svelte";
    import { words } from "#lib/words.ts";
    import AccountMark from "./AccountMark.svelte";
    import { readAccount } from "./account.svelte.ts";
    import AnchoredPanel from "./AnchoredPanel.svelte";
    import { menuPanelWidth } from "./menuWidth.ts";
    import SkatAccountMenu from "./SkatAccountMenu.svelte";

    // The table page's menu key and its panel: the rows a table gives it, and under them the account with the legal
    // links, which a signed-in page carries in no footer. A page without a running table gives it no rows, so the menu
    // holds the account alone. `bar` stands in the top row and opens downwards; `strip` stands last in the bottom strip
    // and opens upwards.
    let {
        place,
        open = $bindable(false),
        key = $bindable(),
        kitWords,
        children,
    }: {
        place: "bar" | "strip";
        open?: boolean;
        key?: HTMLButtonElement | undefined;
        kitWords: KitWords;
        children?: Snippet;
    } = $props();

    // The kit's account menu is this wide; its panel hangs at that width.
    const ACCOUNT_MENU_WIDTH = 256;

    let accountOpen = $state(false);
    let viewportWidth = $state(0);

    const side = $derived(place === "strip" ? "above" : "below");
</script>

<svelte:window bind:innerWidth={viewportWidth} />

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
<AnchoredPanel anchor={key} bind:open {side} width={menuPanelWidth(viewportWidth)} title={words["table.menu"]}>
    <div class="table-menu">
        {@render children?.()}
        <div class="menu-foot">
            <button
                type="button"
                class="row account"
                onclick={() => {
                    open = false;
                    accountOpen = true;
                    void readAccount();
                }}
            >
                <AccountMark />
                <span class="label">{words["account.title"]}</span>
            </button>
        </div>
    </div>
</AnchoredPanel>
<AnchoredPanel
    anchor={key}
    bind:open={accountOpen}
    {side}
    width={ACCOUNT_MENU_WIDTH}
    title={words["account.title"]}
    bare
>
    <SkatAccountMenu
        {kitWords}
        onAccountOpen={() => {
            accountOpen = false;
        }}
    />
</AnchoredPanel>
