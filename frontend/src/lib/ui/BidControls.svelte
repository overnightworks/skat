<script lang="ts">
    import type { BidLadder } from "#lib/bidLadder.ts";
    import { words } from "#lib/words.ts";
    import type { AuctionAction } from "../../routes/(start)/tables.ts";

    const {
        ladder,
        disabled,
        onstep,
    }: {
        ladder: BidLadder;
        disabled: boolean;
        onstep: (action: AuctionAction, value?: number) => void;
    } = $props();

    // Only keyboard focus scrolls: a strip that moved under a pressed pointer would lose the tap.
    function revealInStrip(event: FocusEvent): void {
        const value = event.currentTarget as HTMLElement;
        if (value.matches(":focus-visible")) value.scrollIntoView({ block: "nearest", inline: "center" });
    }
</script>

{#snippet check()}
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
{/snippet}

<div class="bid">
    {#if ladder.kind === "climb"}
        <div class="ladder">
            {#if ladder.held !== null}
                <span class="held">{@render check()}{ladder.held}</span>
            {/if}
            <span class="now">{ladder.lit}</span>
            {#if ladder.rungsBid}
                <div class="higher">
                    {#each ladder.rungs as value (value)}
                        <button
                            type="button"
                            {disabled}
                            onfocus={revealInStrip}
                            onclick={() => {
                                onstep("bid", value);
                            }}
                        >
                            {value}
                        </button>
                    {/each}
                </div>
            {:else}
                {#each ladder.rungs as value (value)}
                    <span>{value}</span>
                {/each}
            {/if}
        </div>
    {/if}
    <div class="bid-buttons">
        {#if ladder.kind === "climb"}
            <button
                type="button"
                class="button button-stage"
                {disabled}
                onclick={() => {
                    onstep(ladder.main.action, ladder.main.value);
                }}
            >
                {#if ladder.main.action === "hold"}
                    {@render check()}
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                    {`${words.hold}`}
                {:else}
                    <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.4"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        aria-hidden="true"
                    >
                        <path d="M12 19V5M6 11l6-6 6 6" />
                    </svg>
                    {ladder.lit}
                {/if}
            </button>
        {/if}
        <button
            type="button"
            class="button button-glass"
            {disabled}
            onclick={() => {
                onstep("pass");
            }}
        >
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.8"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <path d="M6 6l12 12M18 6L6 18" />
            </svg>
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
            {`${words.pass}`}
        </button>
    </div>
</div>
