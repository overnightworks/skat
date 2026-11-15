<script lang="ts">
    import { playOpen, playOpenKey } from "#lib/giveUp.ts";
    import ArmedKey from "#lib/ui/ArmedKey.svelte";
    import { words } from "#lib/words.ts";
    import type { Table } from "../../routes/(start)/tables.ts";

    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

    // The open play is under way from the second tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    async function send(): Promise<void> {
        note = "";
        sentAtVersion = table.version;
        const answer = await playOpen(id, table.version, crypto.randomUUID());
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["table.commandFailed"];
        }
    }
</script>

<!-- A wrong open play cannot be taken back, so the key asks a second tap; a newer version of the table is a new key. -->
{#if playOpenKey(table)}
    {#key table.version}
        <ArmedKey
            class={["copy", "play-open"]}
            idle={words["table.playOpen"]}
            armedWord={words["table.playOpenSure"]}
            disabled={busy}
            onconfirm={() => {
                void send();
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
                    <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
                    <circle cx="12" cy="12" r="3" />
                </svg>
            {/snippet}
        </ArmedKey>
    {/key}
{/if}
