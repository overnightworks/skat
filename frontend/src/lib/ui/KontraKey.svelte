<script lang="ts">
    import { declinableWord, keyWord, wordLabel } from "#lib/kontra.ts";
    import { words } from "#lib/words.ts";
    import { sayKontra, sayNoWord, type Outcome, type Table, type Word } from "../../routes/(start)/tables.ts";

    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

    const word = $derived(keyWord(table));
    const declinable = $derived(declinableWord(table));
    // A word is under way from the tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    async function send(request: (version: number) => Promise<Outcome>): Promise<void> {
        if (busy) return;
        note = "";
        sentAtVersion = table.version;
        const answer = await request(table.version);
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["kontra.commandFailed"];
        }
    }
</script>

{#snippet kontraKey(word: Word)}
    <button
        type="button"
        class="copy kontra"
        disabled={busy}
        onclick={() => send((version) => sayKontra(id, version, crypto.randomUUID(), word))}
    >
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
{/snippet}

{#if word !== null && declinable !== null}
    <div class="kontra-keys">
        {@render kontraKey(word)}
        <button
            type="button"
            class="copy no-word"
            disabled={busy}
            onclick={() => send((version) => sayNoWord(id, version, crypto.randomUUID()))}
        >
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.8"
                stroke-linecap="round"
                aria-hidden="true"
            >
                <path d="M6 6l12 12M18 6L6 18" />
            </svg>
            <span class="label">{words["kontra.decline"]({ word: wordLabel(declinable) })}</span>
        </button>
    </div>
{:else if word !== null}
    {@render kontraKey(word)}
{/if}
