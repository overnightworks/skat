<script lang="ts">
    import { goto } from "$app/navigation";
    import { resolve } from "$app/paths";
    import { closeOnEscape } from "#lib/closeOnEscape.ts";
    import { SERIES_LENGTH_DEFAULT } from "#lib/wire.ts";
    import LockIcon from "#lib/ui/LockIcon.svelte";
    import { words } from "#lib/words.ts";
    import { differs, OFFICIAL, requestOf } from "./openingRules.ts";
    import { createTable, type Visibility } from "./openTable.ts";
    import SettingsBody from "./SettingsBody.svelte";

    let choosing = $state(false);
    let length = $state(SERIES_LENGTH_DEFAULT);
    let visibility = $state<Visibility>("open");
    let infoShown = $state(false);
    let sheet = $state(OFFICIAL);
    let opening = $state(false);
    let failed = $state(false);
    let commandId = crypto.randomUUID();

    // Another length or another request is another command, so a retry never sends two requests under one id,
    // and a sheet that shows what was asked before keeps its id, so a lost answer is replayed, not duplicated.
    function changed(): void {
        commandId = crypto.randomUUID();
    }

    function choose(): void {
        failed = false;
        if (length !== SERIES_LENGTH_DEFAULT || differs(sheet, OFFICIAL)) changed();
        length = SERIES_LENGTH_DEFAULT;
        sheet = OFFICIAL;
        setVisibility("open");
        infoShown = false;
        choosing = true;
    }

    function setVisibility(next: Visibility): void {
        if (next === visibility) return;
        visibility = next;
        changed();
    }

    function close(): void {
        choosing = false;
    }

    async function open(): Promise<void> {
        opening = true;
        const outcome = await createTable(commandId, length, requestOf(sheet), visibility);
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

{#snippet tick()}
    <span class="tick">
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
    </span>
{/snippet}

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
    <div
        class="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={words["start.newTable"]}
        {@attach closeOnEscape(() => {
            if (!opening) close();
        })}
    >
        <h3>{words["start.newTable"]}</h3>
        <button
            type="button"
            class="info"
            aria-label={words["start.visibilityInfoButton"]}
            aria-expanded={infoShown}
            onclick={() => {
                infoShown = !infoShown;
            }}
        ></button>
        <div class="choice" role="radiogroup" aria-label={words["start.visibility"]}>
            <label class="opt" class:on={visibility === "open"}>
                <input
                    type="radio"
                    name="visibility"
                    checked={visibility === "open"}
                    disabled={opening}
                    onchange={() => {
                        setVisibility("open");
                    }}
                />
                {#if visibility === "open"}{@render tick()}{/if}
                <span class="ic">
                    <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        aria-hidden="true"
                    >
                        <circle cx="9" cy="8" r="3.5" />
                        <path
                            d="M2.5 19.5c.7-3.4 3.3-5.2 6.5-5.2s5.8 1.8 6.5 5.2M15.8 4.7a3.5 3.5 0 0 1 0 6.6M18 14.6c2 .7 3.2 2.4 3.5 4.9"
                        />
                    </svg>
                </span>
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                {`${words["start.visibilityOpen"]}`}
            </label>
            <label class="opt" class:on={visibility === "private"}>
                <input
                    type="radio"
                    name="visibility"
                    checked={visibility === "private"}
                    disabled={opening}
                    onchange={() => {
                        setVisibility("private");
                    }}
                />
                {#if visibility === "private"}{@render tick()}{/if}
                <span class="ic"><LockIcon /></span>
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                {`${words["start.visibilityPrivate"]}`}
            </label>
        </div>
        {#if infoShown}
            <p role="status">{words["start.visibilityInfo"]}</p>
        {/if}
        <SettingsBody bind:length bind:sheet disabled={opening} onchange={changed} />
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
