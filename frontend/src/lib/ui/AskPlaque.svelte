<script lang="ts" generics="Answer extends string">
    import type { Snippet } from "svelte";

    import type { AskView } from "#lib/giveUp.ts";
    import { Marked } from "overnightworks-design";

    const {
        view,
        disabled,
        onanswer,
        children,
    }: {
        view: AskView<Answer>;
        disabled: boolean;
        onanswer: (answer: Answer) => void;
        children?: Snippet;
    } = $props();
</script>

{#snippet level({ text }: { text: string })}<b>{text}</b>{/snippet}

<div class="plaque ask">
    <span class="game">
        {#each view.faces as face (face.seat)}
            <span class="face" aria-hidden="true">{face.initial}</span>
        {/each}
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {view.text} compiles to a `?? ""` branch no text can take -->
        {`${view.text}`}
        {#if view.waits}
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        {/if}
    </span>
    {#if view.then}
        <span class="game">
            {#each view.then.faces as face (face.seat)}
                <span class="face" aria-hidden="true">{face.initial}</span>
            {/each}
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {view.then.text} compiles to a `?? ""` branch no text can take -->
            {`${view.then.text}`}
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </span>
    {/if}
    {#if view.demand}
        <div class="game pushes"><Marked parts={view.demand} marked={{ level }} /></div>
    {/if}
    {@render children?.()}
    {#if view.buttons.length > 0}
        <div class="answers">
            {#each view.buttons as button (button.answer)}
                <button
                    type="button"
                    class={`button ${button.primary ? "button-stage" : "button-glass"}`}
                    {disabled}
                    onclick={() => {
                        onanswer(button.answer);
                    }}
                >
                    {#if button.icon === "check"}
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
                    {:else if button.icon === "cross"}
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
                    {:else}
                        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M8 5l11 7-11 7z" />
                        </svg>
                    {/if}
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {button.word} compiles to a `?? ""` branch no word can take -->
                    {`${button.word}`}
                </button>
            {/each}
        </div>
    {/if}
</div>
