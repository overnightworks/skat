<script lang="ts">
    import { standTap } from "#lib/openChair.ts";
    import { words } from "#lib/words.ts";

    const ARMED_MILLISECONDS = 3000;

    // `handRuns` makes the key round on a phone and asks a second tap of it; between hands one tap stands up.
    const { handRuns, onstand }: { handRuns: boolean; onstand: () => void } = $props();

    let armed = $state(false);
    let key: HTMLButtonElement | undefined;
    let disarmTimer: ReturnType<typeof setTimeout> | undefined;

    const label = $derived(armed ? words["table.standUpArmed"] : words["table.standUp"]);

    function disarm(): void {
        clearTimeout(disarmTimer);
        armed = false;
    }

    function tap(): void {
        if (standTap(handRuns, armed) === "arm") {
            armed = true;
            disarmTimer = setTimeout(disarm, ARMED_MILLISECONDS);
        } else {
            disarm();
            onstand();
        }
    }

    $effect(() => disarm);
</script>

<!-- A tap anywhere else puts the armed key back, so the second tap is always the same person's second thought. -->
<svelte:window
    onpointerdown={(event: PointerEvent) => {
        if (!key?.contains(event.target as Node)) disarm();
    }}
/>

<button
    bind:this={key}
    type="button"
    class="copy stand"
    class:round={handRuns}
    class:arm={armed}
    title={label}
    onclick={tap}
>
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
    <span class="label">{label}</span>
    {#if armed}
        <i class="drain" aria-hidden="true"></i>
    {/if}
</button>
