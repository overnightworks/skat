<script lang="ts">
    import type { WeiterBar } from "#lib/result.ts";
    import { words } from "#lib/words.ts";

    // The key of the bar after a game: „Weiter“ (after the series' last game „Neue Serie“) until the viewer has tapped,
    // then who is awaited. A watcher of the standings has neither and says so. `sent` is a tap under way.
    const {
        bar,
        watching,
        newSeries,
        sent,
        ontap,
    }: { bar: WeiterBar | null; watching: boolean; newSeries: boolean; sent: boolean; ontap: () => void } = $props();
</script>

{#if bar?.kind === "tap"}
    <button type="button" class="copy weiter" disabled={sent && !bar.again} onclick={ontap}>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M5 12.5l4.5 4.5L19 7" />
        </svg>
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
        {`${newSeries ? words["table.newSeries"] : words["table.weiter"]}`}
    </button>
{:else if bar !== null}
    <span class="copy wait" role="status">
        <span class="words">{bar.text}</span>
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    </span>
{:else if watching}
    <span class="copy watching" role="status">
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
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
        {`${words["table.watchingOnly"]}`}
    </span>
{/if}
