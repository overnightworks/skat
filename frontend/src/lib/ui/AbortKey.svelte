<script lang="ts">
    import { onDestroy } from "svelte";
    import { abortView } from "#lib/abort.ts";
    import { words } from "#lib/words.ts";
    import { answerAbort, type Table } from "../../routes/(start)/tables.ts";

    const ARMED_MILLISECONDS = 3000;

    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

    const offered = $derived(abortView(table).offered);
    // The first tap arms the key and the second, within three seconds, sends the yes.
    let armed = $state(false);
    let disarmTimer: ReturnType<typeof setTimeout> | undefined;
    // The yes is under way from the second tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    onDestroy(() => {
        clearTimeout(disarmTimer);
    });

    async function tap(): Promise<void> {
        clearTimeout(disarmTimer);
        if (!armed) {
            armed = true;
            disarmTimer = setTimeout(() => (armed = false), ARMED_MILLISECONDS);
            return;
        }
        armed = false;
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
    <button type="button" class="copy abort" class:arm={armed} disabled={busy} onclick={tap}>
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="3" />
        </svg>
        <span class="label">{armed ? words["table.abortSure"] : words["table.abort"]}</span>
        {#if armed}
            <i aria-hidden="true"></i>
        {/if}
    </button>
{/if}
