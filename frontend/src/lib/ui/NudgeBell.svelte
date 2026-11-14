<script lang="ts">
    import { ASK_AGAIN_AFTER } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import type { Nudge } from "../../routes/(start)/nudge.ts";
    import { nudgeSeat } from "../../routes/(start)/nudge.ts";

    const MILLISECONDS_PER_SECOND = 1000;

    // The bell is offered ASK_AGAIN_AFTER after it first saw a chair at a version with a number of nudges, and its minute
    // starts anew whenever either changes; a page that saw it late offers it late, and the server decides whether its
    // minute has passed. A chair nobody has to nudge has no nudge and no bell. The own bell shakes once, when the page
    // sees the nudge arrive; a reload sees it already made and draws it at rest.
    const {
        id,
        version,
        seat,
        name,
        nudge,
        shaking,
    }: { id: string; version: number; seat: number; name: string; nudge: Nudge | null; shaking: boolean } = $props();

    const sight = $derived(`${String(version)}:${String(nudge?.nudges)}`);
    let offeredFor = $state("");
    const offered = $derived(offeredFor === sight);
    $effect(() => {
        const seen = sight;
        const timer = setTimeout(() => {
            offeredFor = seen;
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

{#if nudge !== null}
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
{/if}
