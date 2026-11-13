<script lang="ts">
    import { abortView } from "#lib/abort.ts";
    import ArmedKey from "#lib/ui/ArmedKey.svelte";
    import { words } from "#lib/words.ts";
    import { answerAbort, type Table } from "../../routes/(start)/tables.ts";

    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

    const offered = $derived(abortView(table).offered);
    // The yes is under way from the second tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    async function agree(): Promise<void> {
        note = "";
        sentAtVersion = table.version;
        const answer = await answerAbort(id, crypto.randomUUID(), "agree");
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["table.commandFailed"];
        }
    }
</script>

{#if offered}
    <ArmedKey
        class="copy abort"
        idle={words["table.abort"]}
        armedWord={words["table.abortSure"]}
        disarmOnOtherTap={false}
        disabled={busy}
        onconfirm={() => {
            void agree();
        }}
    >
        {#snippet icon()}
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <rect x="6" y="6" width="12" height="12" rx="3" />
            </svg>
        {/snippet}
    </ArmedKey>
{/if}
