<script lang="ts">
    import type { GiveUpView } from "#lib/giveUp.ts";
    import { words } from "#lib/words.ts";
    import type { GiveUpAnswer } from "../../routes/(start)/tables.ts";

    const {
        view,
        disabled,
        onanswer,
    }: { view: GiveUpView; disabled: boolean; onanswer: (answer: GiveUpAnswer) => void } = $props();
</script>

<div class="plaque ask">
    <span class="game">
        {#each view.faces as face (face.seat)}
            <span class="face" aria-hidden="true">{face.initial}</span>
        {/each}
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {view.text} compiles to a `?? ""` branch no text can take -->
        {`${view.text}`}
        {#if view.line === "waits"}
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
        {/if}
    </span>
    {#if view.answers.length > 0}
        <div class="answers">
            {#if view.answers.includes("agree")}
                <button
                    type="button"
                    class="button button-stage"
                    {disabled}
                    onclick={() => {
                        onanswer("agree");
                    }}
                >
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
                    {`${words["table.accept"]}`}
                </button>
            {/if}
            {#if view.answers.includes("decline")}
                <button
                    type="button"
                    class="button button-glass"
                    {disabled}
                    onclick={() => {
                        onanswer("decline");
                    }}
                >
                    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M8 5l11 7-11 7z" />
                    </svg>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                    {`${words["table.playOn"]}`}
                </button>
            {/if}
        </div>
    {/if}
</div>
