<script lang="ts">
    import ArmedKey from "#lib/ui/ArmedKey.svelte";
    import { words } from "#lib/words.ts";

    // `handRuns` makes the key round on a phone and asks a second tap of it; between hands one tap stands up.
    const { handRuns, onstand }: { handRuns: boolean; onstand: () => void } = $props();
</script>

<ArmedKey
    class={["copy", "stand", handRuns && "round"]}
    idle={words["table.standUp"]}
    armedWord={words["table.standUpArmed"]}
    arms={handRuns}
    onconfirm={onstand}
>
    {#snippet icon()}
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M4.5 4v16M4.5 13.5h8.5v6.5" />
            <path d="M18.5 15V4M15 7.5l3.5-3.5L22 7.5" />
        </svg>
    {/snippet}
</ArmedKey>
