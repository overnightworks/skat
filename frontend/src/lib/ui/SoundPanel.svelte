<script module lang="ts">
    export interface SoundChoice {
        readonly id: string;
        readonly name: string;
        readonly pick: () => void;
    }

    /** What the panel draws: a switch, the volume slider or a pick among a few names. */
    export type SoundRow =
        | {
              readonly kind: "switch";
              readonly label: string;
              readonly on: boolean;
              readonly change: (on: boolean) => void;
          }
        | {
              readonly kind: "volume";
              readonly label: string;
              readonly value: number;
              readonly change: (value: number) => void;
          }
        | {
              readonly kind: "choice";
              readonly label: string;
              readonly options: readonly SoundChoice[];
              readonly picked: string;
              /** The pick shows but cannot change. */
              readonly greyed: boolean;
              readonly note?: string;
              /** The word beside the label that says the pick just sounded. */
              readonly played?: string;
          };
</script>

<script lang="ts">
    import { words } from "#lib/words.ts";
    import type { Attachment } from "svelte/attachments";

    const { title, rows }: { title: string; rows: readonly SoundRow[] } = $props();

    let body: HTMLDivElement | undefined = $state();
    let content: HTMLDivElement | undefined = $state();
    let moreBelow = $state(false);

    function measure(): void {
        if (body !== undefined) moreBelow = body.scrollHeight - body.scrollTop - body.clientHeight > 1;
    }

    // The body changes size when the panel opens and when the viewport resizes; its content when the rows change.
    $effect(() => {
        if (body === undefined || content === undefined) return;
        const watcher = new ResizeObserver(measure);
        watcher.observe(body);
        watcher.observe(content);
        return () => {
            watcher.disconnect();
        };
    });

    // The stylesheet's filled track reads the volume from the element, set as a property so no style attribute carries it.
    function showVolume(value: number): Attachment<HTMLElement> {
        return (element) => {
            element.style.setProperty("--volume", String(value));
        };
    }
</script>

{#snippet speaker()}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" />
        <path d="M15.5 9.2a4 4 0 0 1 0 5.6" />
        <path d="M18.3 6.6a7.8 7.8 0 0 1 0 10.8" />
    </svg>
{/snippet}

<div class="sound-head">
    {@render speaker()}
    {title}
</div>
<div class="sound-body" bind:this={body} onscroll={measure}>
    <div bind:this={content}>
        {#each rows as row (row.label)}
            {#if row.kind === "switch"}
                <label class="sound-row">
                    <span class="sound-row-name">{row.label}</span>
                    <input
                        type="checkbox"
                        role="switch"
                        class="sound-switch"
                        checked={row.on}
                        onchange={(event) => {
                            row.change(event.currentTarget.checked);
                        }}
                    />
                </label>
            {:else if row.kind === "volume"}
                <label class="sound-row sound-volume">
                    <span class="sound-row-name">{row.label}</span>
                    <output class="sound-value">{row.value}</output>
                    <input
                        type="range"
                        class="sound-slider"
                        aria-label={row.label}
                        min="0"
                        max="100"
                        step="1"
                        value={row.value}
                        {@attach showVolume(row.value)}
                        oninput={(event) => {
                            row.change(event.currentTarget.valueAsNumber);
                        }}
                    />
                </label>
            {:else}
                <div
                    class="sound-row sound-stack"
                    class:greyed={row.greyed}
                    role="radiogroup"
                    aria-label={row.label}
                    aria-disabled={row.greyed}
                >
                    <span class="sound-row-name">{row.label}</span>
                    {#if row.played !== undefined}
                        <span class="sound-played">{@render speaker()}{row.played}</span>
                    {/if}
                    <div class="sound-segments">
                        {#each row.options as option (option.id)}
                            <label class="sound-option">
                                <input
                                    type="radio"
                                    name={row.label}
                                    checked={option.id === row.picked}
                                    disabled={row.greyed}
                                    onchange={option.pick}
                                />
                                <span class="sound-option-face">
                                    {#if option.id === row.picked}
                                        <svg
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            stroke-width="2.8"
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg
                                        >
                                    {/if}
                                    {option.name}
                                </span>
                            </label>
                        {/each}
                    </div>
                    {#if row.note !== undefined}
                        <p class="sound-note">{row.note}</p>
                    {/if}
                </div>
            {/if}
        {/each}
    </div>
</div>
<div class="sound-more" class:shown={moreBelow} aria-hidden="true">
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg
    >
    {words["sound.more"]}
</div>
