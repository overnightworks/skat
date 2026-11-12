<script lang="ts">
    import { goto } from "$app/navigation";
    import { resolve } from "$app/paths";
    import { SERIES_LENGTH_DEFAULT, SERIES_LENGTH_MAX, SERIES_LENGTH_MIN, SERIES_LENGTH_STEP } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import { createTable } from "./tables.ts";

    let choosing = $state(false);
    let length = $state(SERIES_LENGTH_DEFAULT);
    let opening = $state(false);
    let failed = $state(false);
    let commandId = crypto.randomUUID();

    function choose(): void {
        failed = false;
        setLength(SERIES_LENGTH_DEFAULT);
        choosing = true;
    }

    function setLength(next: number): void {
        if (next === length) return;
        length = next;
        // Another length is another command, so a retry never sends two requests under one id.
        commandId = crypto.randomUUID();
    }

    function step(by: number): void {
        setLength(length + by);
    }

    function close(): void {
        choosing = false;
    }

    async function open(): Promise<void> {
        opening = true;
        const outcome = await createTable(commandId, length);
        opening = false;
        failed = outcome.kind !== "table";
        if (outcome.kind === "table") {
            // The next table is another command, even when the browser restores this page from its cache.
            commandId = crypto.randomUUID();
            choosing = false;
            await goto(resolve("/(start)/t/[id]", { id: outcome.table.id }));
        }
    }
</script>

<div class="new-table">
    <button type="button" onclick={choose}>
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
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
        {`${words["start.newTable"]}`}
    </button>
</div>
{#if choosing}
    <div class="scrim"></div>
    <div class="sheet" role="dialog" aria-modal="true" aria-label={words["start.newTable"]}>
        <h3>{words["start.newTable"]}</h3>
        <div class="stepper" role="group" aria-label={words["start.seriesLength"]}>
            <button
                type="button"
                class="step"
                aria-label={words["start.seriesFewer"]}
                disabled={length <= SERIES_LENGTH_MIN || opening}
                onclick={() => {
                    step(-SERIES_LENGTH_STEP);
                }}
            >
                −
            </button>
            <span
                class="value"
                role="spinbutton"
                tabindex="0"
                aria-valuemin={SERIES_LENGTH_MIN}
                aria-valuemax={SERIES_LENGTH_MAX}
                aria-valuenow={length}
                aria-label={words["start.seriesGames"](length)}
            >
                {length}<small>{words["start.seriesGames"](length)}</small>
            </span>
            <button
                type="button"
                class="step"
                aria-label={words["start.seriesMore"]}
                disabled={length >= SERIES_LENGTH_MAX || opening}
                onclick={() => {
                    step(SERIES_LENGTH_STEP);
                }}
            >
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.6"
                    stroke-linecap="round"
                    aria-hidden="true"
                >
                    <path d="M12 5v14M5 12h14" />
                </svg>
            </button>
        </div>
        {#if failed}
            <p role="alert">{words["start.newTableFailed"]}</p>
        {/if}
        <div class="btns">
            <button type="button" class="confirm" disabled={opening} onclick={open}>
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                >
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                </svg>
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                {`${words["start.openTable"]}`}
            </button>
            <button type="button" class="cancel" disabled={opening} onclick={close}>
                {words["start.cancelNewTable"]}
            </button>
        </div>
    </div>
{/if}
