<script lang="ts">
    import { tableRules } from "#lib/tableRules.ts";
    import RuleMark from "#lib/ui/RuleMark.svelte";
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
                    <RuleMark id={chip.id} />{chip.word}
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
                <span class="ic"><RuleMark id={row.id} /></span>
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
