<script lang="ts">
    import type { Bubble } from "#lib/auctionMarks.ts";
    import { words } from "#lib/words.ts";

    // A bubble springs up when this page saw its word said; the table already showing it stands still. A bid stands as
    // its number, a „Ja“ and a „Weg“ as their word behind a mark, since the counter carries the value they answer.
    const { bubble, initial, fresh }: { bubble: Bubble | null; initial: string; fresh: boolean } = $props();

    const QUIET = {
        hold: { mark: "M5 12.5l4.5 4.5L19 7.5", word: words["bid.hold"] },
        pass: { mark: "M6 6l12 12M18 6L6 18", word: words["bid.pass"] },
    };
</script>

{#snippet said(text: string | number)}<span class="said">{text}</span>{/snippet}

{#if bubble}
    {#key `${bubble.kind}${String(bubble.value)}`}
        <span class="bubble" class:quiet={bubble.kind !== "bid"} class:fresh>
            <span class="dot" aria-hidden="true">{initial}</span>
            {#if bubble.kind === "bid"}
                {@render said(bubble.value)}
            {:else}
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                >
                    <path d={QUIET[bubble.kind].mark} />
                </svg>
                {@render said(QUIET[bubble.kind].word)}
            {/if}
        </span>
    {/key}
{/if}
