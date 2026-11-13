<script lang="ts">
    import { keyWord, wordLabel } from "#lib/kontra.ts";
    import { words } from "#lib/words.ts";
    import { sayKontra, type Table } from "../../routes/(start)/tables.ts";

    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

    const word = $derived(keyWord(table));
    // A word is under way from the tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    async function say(): Promise<void> {
        if (word === null || busy) return;
        note = "";
        sentAtVersion = table.version;
        const answer = await sayKontra(id, table.version, crypto.randomUUID(), word);
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["kontra.commandFailed"];
        }
    }
</script>

{#if word !== null}
    <button type="button" class="copy kontra" disabled={busy} onclick={say}>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M13 3L5 14h6l-1 7 8-11h-6z" />
        </svg>
        <span class="label">{wordLabel(word)}</span>
    </button>
{/if}
