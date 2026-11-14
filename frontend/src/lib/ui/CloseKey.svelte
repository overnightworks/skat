<script lang="ts">
    import { words } from "#lib/words.ts";
    import { closeTable } from "../../routes/(start)/tables.ts";

    // The opener's key: one tap asks, "Schließen" sends the close, "Abbrechen" asks no more and sends nothing.
    let { id, note = $bindable() }: { id: string; note: string } = $props();

    let asking = $state(false);

    async function confirm(): Promise<void> {
        asking = false;
        note = "";
        if ((await closeTable(id, crypto.randomUUID())).kind !== "table") note = words["table.commandFailed"];
    }
</script>

{#snippet power()}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path d="M12 3v8.5" />
        <path d="M7.2 6.2a7.5 7.5 0 1 0 9.6 0" />
    </svg>
{/snippet}

<button
    type="button"
    class="copy close"
    title={words["table.close"]}
    onclick={() => {
        asking = true;
    }}
>
    {@render power()}
    <span class="label">{words["table.close"]}</span>
</button>
{#if asking}
    <div class="scrim"></div>
    <div class="sheet question" role="dialog" aria-modal="true" aria-label={words["table.closeQuestion"]}>
        <span class="glyph">{@render power()}</span>
        <h3>{words["table.closeQuestion"]}</h3>
        <div class="btns">
            <button type="button" class="confirm leave" onclick={confirm}>
                {@render power()}
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                {`${words["table.closeConfirm"]}`}
            </button>
            <button
                type="button"
                class="cancel"
                onclick={() => {
                    asking = false;
                }}
            >
                {words["table.closeCancel"]}
            </button>
        </div>
    </div>
{/if}
