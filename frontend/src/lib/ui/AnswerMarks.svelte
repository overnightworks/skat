<script lang="ts">
    import type { AnswerMark } from "#lib/giveUp.ts";
    import { words } from "#lib/words.ts";

    const { mark }: { mark: AnswerMark | undefined } = $props();
</script>

{#if mark === "declined"}
    <span class="mark declined" title={words["table.saidNo"]}>
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
    </span>
{:else if mark === "agreed"}
    <span class="mark agreed" title={words["table.saidYes"]}>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M5 12.5l4.5 4.5L19 7" />
        </svg>
    </span>
{:else if mark === "open"}
    <span class="mark open-play" title={words["table.playsOpenMark"]}>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
            <circle cx="12" cy="12" r="3" />
        </svg>
    </span>
{:else if mark === "ready"}
    <span class="mark ready" title={words["table.readyMark"]}>
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M5 12.5l4.5 4.5L19 7" />
        </svg>
    </span>
{:else if mark === "unready"}
    <span class="mark waits" title={words["table.notReadyMark"]}>
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    </span>
{:else if mark === "unanswered"}
    <span class="mark unanswered" title={words["table.noAnswerYet"]}>
        <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
    </span>
{/if}
