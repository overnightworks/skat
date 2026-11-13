<script lang="ts">
    import { tableRules, type ChipId, type RuleId } from "#lib/tableRules.ts";
    import { words } from "#lib/words.ts";

    import type { Bock, Options } from "../../routes/(start)/tables.ts";

    let { options, bock }: { options: Options; bock: Bock | null } = $props();

    const rules = $derived(tableRules(options, bock));
    let chips: HTMLButtonElement | undefined = $state();
    let sheet: HTMLDialogElement | undefined = $state();
    let lockInfoShown = $state(false);

    function open(): void {
        lockInfoShown = false;
        sheet?.showModal();
    }
</script>

{#snippet mark(id: ChipId | RuleId)}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        {#if id === "points"}
            <path d="M18 5H6l6 7-6 7h12" />
        {:else if id === "kontra"}
            <path d="M13 3L5 14h6l-1 7 8-11h-6z" />
        {:else if id === "ramsch"}
            <path d="M12 4v10M7 10l5 5 5-5M5 20h14" />
        {:else if id === "pushing"}
            <path d="M4 12h14M13 6l6 6-6 6" />
        {:else if id === "bock"}
            <g stroke-width="1.8">
                <rect x="4" y="4" width="16" height="16" rx="4" />
                <circle cx="9" cy="9" r="1.2" fill="currentColor" stroke="none" />
                <circle cx="15" cy="15" r="1.2" fill="currentColor" stroke="none" />
                <circle cx="15" cy="9" r="1.2" fill="currentColor" stroke="none" />
                <circle cx="9" cy="15" r="1.2" fill="currentColor" stroke="none" />
            </g>
        {:else}
            <path d="M5 12.5l4.5 4.5L19 7.5" />
        {/if}
    </svg>
{/snippet}

<div class="rules-slot">
    <button
        bind:this={chips}
        type="button"
        class="rulepill"
        aria-haspopup="dialog"
        aria-label={words["rules.button"]}
        onclick={open}
    >
        <span class="chips">
            {#each rules.chips as chip (chip.id)}
                <span class="chip" class:official={chip.id === "official"}>
                    {@render mark(chip.id)}{chip.word}
                    {#if chip.count !== null}
                        <b class="n" aria-label={chip.count.label}>{chip.count.number}</b>
                    {/if}
                </span>
            {/each}
        </span>
    </button>
</div>
<dialog
    bind:this={sheet}
    class="rules-sheet"
    aria-label={words["rules.title"]}
    onclose={() => {
        chips?.focus();
    }}
>
    <h3>{words["rules.title"]}</h3>
    <span class="lockbadge">
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <rect x="5" y="10.5" width="14" height="10" rx="2.5" />
            <path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3" />
        </svg>
        {words["rules.lockBadge"]}
        <button
            type="button"
            class="info"
            aria-label={words["rules.info"]}
            aria-expanded={lockInfoShown}
            aria-controls="rules-lock-info"
            onclick={() => {
                lockInfoShown = !lockInfoShown;
            }}
        >
            i
        </button>
    </span>
    {#if lockInfoShown}
        <p id="rules-lock-info" class="lockinfo">{words["rules.lockInfo"]}</p>
    {/if}
    <div class="rrows">
        {#each rules.rows as row (row.id)}
            <div class="rrow">
                <span class="ic">{@render mark(row.id)}</span>
                <span class="txt">
                    <b>{row.name}</b>
                    <small>
                        {#each row.settings as setting (setting)}
                            <span>{setting}</span>
                        {/each}
                    </small>
                </span>
            </div>
        {/each}
    </div>
    <div class="btns">
        <button
            type="button"
            class="button-glass"
            onclick={() => {
                sheet?.close();
            }}
        >
            {words["rules.close"]}
        </button>
    </div>
</dialog>
