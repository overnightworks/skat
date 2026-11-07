<script lang="ts">
    import { goto } from "$app/navigation";
    import { resolve } from "$app/paths";
    import "./tables.css";
    import { createTable } from "./tables.ts";

    let opening = $state(false);
    let failed = $state(false);
    let commandId = crypto.randomUUID();

    async function open(): Promise<void> {
        opening = true;
        const outcome = await createTable(commandId);
        opening = false;
        failed = outcome.kind !== "table";
        if (outcome.kind === "table") {
            // The next table is another command, even when the browser restores this page from its cache.
            commandId = crypto.randomUUID();
            await goto(resolve("/(start)/t/[id]", { id: outcome.table.id }));
        }
    }
</script>

<div class="new-table" lang="de">
    <button type="button" disabled={opening} onclick={open}>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            aria-hidden="true"
        >
            <path d="M12 5v14M5 12h14" />
        </svg>
        Neuer Tisch
    </button>
    {#if failed}
        <p role="alert">Der Tisch konnte nicht eröffnet werden.</p>
    {/if}
</div>
