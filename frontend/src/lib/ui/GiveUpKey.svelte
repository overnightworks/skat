<script lang="ts">
    import { giveUpKey } from "#lib/giveUp.ts";
    import ArmedKey from "#lib/ui/ArmedKey.svelte";
    import { words } from "#lib/words.ts";
    import { giveUp, type Table } from "../../routes/(start)/tables.ts";

    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

    const key = $derived(giveUpKey(table));
    // The give-up is under way from the second tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    async function send(): Promise<void> {
        note = "";
        sentAtVersion = table.version;
        const answer = await giveUp(id, table.version, crypto.randomUUID());
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["table.commandFailed"];
        }
    }
</script>

<!-- A newer version of the table, a card played among them, is a new key: it comes back disarmed. -->
{#if key !== null}
    {#key table.version}
        <ArmedKey
            class={["copy", "give-up", key.round && "round"]}
            idle={words["table.giveUp"]}
            armedWord={words["table.giveUpSure"]}
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
                    aria-hidden="true"
                >
                    <path d="M5 21V3.5" />
                    <path d="M5 4.5c4-2 7 2 11.5 0v8.5c-4.5 2-7.5-2-11.5 0z" fill="currentColor" />
                </svg>
            {/snippet}
        </ArmedKey>
    {/key}
{/if}
