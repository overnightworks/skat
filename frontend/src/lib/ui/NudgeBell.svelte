<script lang="ts">
    import { ASK_AGAIN_AFTER } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import Cowbell from "./Cowbell.svelte";
    import type { Nudge } from "../../routes/(start)/nudge.ts";
    import { nudgeSeat } from "../../routes/(start)/nudge.ts";

    const MILLISECONDS_PER_SECOND = 1000;

    // The bell is offered ASK_AGAIN_AFTER after it first saw a chair at a version with a number of nudges, and its minute
    // starts anew whenever either changes; a page that saw it late offers it late, and the server decides whether its
    // minute has passed. A chair nobody has to nudge has no nudge and no bell. The nudge's answer is the cowbell over the
    // chair and the line it grumbles, for as long as `grumble` holds a line; a nudge made earlier leaves nothing.
    const {
        id,
        version,
        seat,
        name,
        nudge,
        grumble,
    }: { id: string; version: number; seat: number; name: string; nudge: Nudge | null; grumble: string | null } =
        $props();

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
    {/if}
{/if}

{#if grumble !== null}
    <Cowbell />
    <span class="bubble word grumble">
        <span class="dot" aria-hidden="true">{name.slice(0, 1)}</span>
        <span class="said">{grumble}</span>
    </span>
{/if}
