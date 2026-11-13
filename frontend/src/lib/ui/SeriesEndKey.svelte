<script lang="ts">
    import { seriesEndOffered } from "#lib/series.ts";
    import ArmedKey from "#lib/ui/ArmedKey.svelte";
    import { words } from "#lib/words.ts";
    import { answerSeriesEnd, type Table } from "../../routes/(start)/tables.ts";

    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

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
        class={["copy", "end-series", "round"]}
        idle={words["table.endSeries"]}
        armedWord={words["table.endSeriesSure"]}
        disarmOnOtherTap={false}
        disabled={busy}
        onconfirm={() => {
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
