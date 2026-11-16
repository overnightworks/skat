<script lang="ts">
    import { seriesEndOffered } from "#lib/series.ts";
    import ArmedKey from "#lib/ui/ArmedKey.svelte";
    import { words } from "#lib/words.ts";
    import { answerSeriesEnd, type Table } from "../../routes/(start)/tables.ts";

    // `onsent` is told when the second tap sends the yes, so the menu that holds the row can close.
    let {
        id,
        table,
        note = $bindable(),
        onsent,
    }: { id: string; table: Table; note: string; onsent?: () => void } = $props();

    const offered = $derived(seriesEndOffered(table));
    // The yes is under way from the second tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    async function propose(): Promise<void> {
        note = "";
        sentAtVersion = table.version;
        const answer = await answerSeriesEnd(id, crypto.randomUUID(), "agree");
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["table.commandFailed"];
        }
    }
</script>

{#if offered}
    <ArmedKey
        class="row end-series"
        idle={words["table.endSeries"]}
        armedWord={words["table.endSeriesSure"]}
        disarmOnOtherTap={false}
        disabled={busy}
        onconfirm={() => {
            onsent?.();
            void propose();
        }}
    >
        {#snippet icon()}
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <path d="M5 21V4M5 5h12l-2.5 4 2.5 4H5" />
            </svg>
        {/snippet}
    </ArmedKey>
{/if}
