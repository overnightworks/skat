<script lang="ts">
    import { onMount } from "svelte";
    import { ASK_AGAIN_AFTER } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import type { Nudge } from "../../routes/(start)/nudge.ts";
    import { nudgeSeat } from "../../routes/(start)/tables.ts";

    const MILLISECONDS_PER_SECOND = 1000;

    // The page mounts one bell for each sight of a chair at a version with a number of nudges, so the bell is offered
    // ASK_AGAIN_AFTER after it was first seen so; a page that saw it late offers it late, and the server decides whether
    // its minute has passed.
    const {
        id,
        version,
        seat,
        name,
        nudge,
        shaking,
    }: { id: string; version: number; seat: number; name: string; nudge: Nudge; shaking: boolean } = $props();

    let offered = $state(false);
    onMount(() => {
        const timer = setTimeout(() => {
            offered = true;
        }, ASK_AGAIN_AFTER * MILLISECONDS_PER_SECOND);
        return () => {
            clearTimeout(timer);
        };
    });
</script>

{#snippet bell()}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.9"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path d="M6 17V11a6 6 0 0 1 12 0v6l1.5 1.5h-15z" />
        <path d="M10 21.2a2.2 2.2 0 0 0 4 0" />
    </svg>
{/snippet}

{#if offered && nudge.may_nudge}
    <button
        type="button"
        class="mark bell"
        title={`${name} ${words["table.nudge"]}`}
        aria-label={`${name} ${words["table.nudge"]}`}
        onclick={() => {
            void nudgeSeat(id, version, seat, nudge.nudges);
        }}
    >
        {@render bell()}
    </button>
{:else if nudge.nudges > 0}
    <span class="mark bell belled" class:shaken={shaking} role="img" aria-label={words["table.nudged"]}>
        {@render bell()}
        <i aria-hidden="true">
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.8"
                stroke-linecap="round"
                stroke-linejoin="round"
            >
                <path d="M5 12.5l4.5 4.5L19 7.5" />
            </svg>
        </i>
    </span>
{/if}
