<script lang="ts">
    import { shorten, shortenKey } from "#lib/giveUp.ts";
    import { words } from "#lib/words.ts";
    import type { Table } from "../../routes/(start)/tables.ts";

    // `onsent` is told when the tap sends the request, so the menu that holds the row can close.
    let {
        id,
        table,
        note = $bindable(),
        onsent,
    }: { id: string; table: Table; note: string; onsent?: () => void } = $props();

    // The request is under way from the tap until the stream brings a newer version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    async function send(): Promise<void> {
        note = "";
        sentAtVersion = table.version;
        const answer = await shorten(id, table.version, crypto.randomUUID());
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["table.commandFailed"];
        }
    }
</script>

{#if shortenKey(table)}
    <button
        type="button"
        class="row shorten"
        title={words["table.shorten"]}
        disabled={busy}
        onclick={() => {
            onsent?.();
            void send();
        }}
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
            <path d="M4 6l7 6-7 6zM12.5 6l7 6-7 6z" />
            <path d="M21 6v12" />
        </svg>
        <span class="label">{words["table.shorten"]}</span>
    </button>
{/if}
