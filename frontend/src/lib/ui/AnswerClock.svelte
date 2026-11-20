<script lang="ts">
    import { onMount } from "svelte";

    import { secondsLeft, clockText } from "#lib/answerClock.ts";
    import { words } from "#lib/words.ts";

    // `until` is the instant a silent seat counts as no; the line counts down to it and stays at 0:00 until the table
    // brings the answer. `ends` says that the silence ends the table, as it does at the series' end.
    const { until, ends = false }: { until: string; ends?: boolean } = $props();

    let now = $state(Date.now());
    onMount(() => {
        const tick = setInterval(() => {
            now = Date.now();
        }, 1000);
        return () => {
            clearInterval(tick);
        };
    });
    const time = $derived(clockText(secondsLeft(until, now)));
</script>

<div class="clockline">
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        aria-hidden="true"
    >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
    </svg>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[...]} compiles to a `?? ""` branch no text can take -->
    <span>{`${words[ends ? "table.answerClockEnds" : "table.answerClock"]({ time })}`}</span>
</div>
