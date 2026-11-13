<script lang="ts">
    import type { Snippet } from "svelte";
    import type { ClassValue } from "svelte/elements";

    // The first tap arms the key for this long; only a second tap inside the time confirms.
    const ARMED_MILLISECONDS = 3000;

    const {
        class: className,
        idle,
        armedWord,
        icon,
        onconfirm,
        arms = true,
        disarmOnOtherTap = true,
        disabled = false,
    }: {
        class: ClassValue;
        idle: string;
        armedWord: string;
        icon?: Snippet;
        onconfirm: () => void;
        // A key that does not arm confirms on its first tap.
        arms?: boolean;
        // A press anywhere else puts the armed key back; without it the time alone does.
        disarmOnOtherTap?: boolean;
        disabled?: boolean;
    } = $props();

    let armed = $state(false);
    let key: HTMLButtonElement | undefined;
    let disarmTimer: ReturnType<typeof setTimeout> | undefined;

    const word = $derived(armed ? armedWord : idle);

    function disarm(): void {
        clearTimeout(disarmTimer);
        armed = false;
    }

    function tap(): void {
        clearTimeout(disarmTimer);
        if (arms && !armed) {
            armed = true;
            disarmTimer = setTimeout(disarm, ARMED_MILLISECONDS);
        } else {
            disarm();
            onconfirm();
        }
    }

    $effect(() => disarm);
</script>

<svelte:window
    onpointerdown={(event: PointerEvent) => {
        if (disarmOnOtherTap && !key?.contains(event.target as Node)) disarm();
    }}
/>

<button
    bind:this={key}
    type="button"
    class={["armed-key", className, armed && "arm"]}
    {disabled}
    title={word}
    onclick={tap}
>
    {@render icon?.()}
    <span class="label">{word}</span>
    {#if armed}
        <i class="run-out" aria-hidden="true"></i>
    {/if}
</button>
