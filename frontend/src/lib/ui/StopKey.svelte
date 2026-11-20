<script lang="ts">
    import { words } from "#lib/words.ts";

    // „Aufhören“ at the series' end: the table ends for everyone. `sent` is a tap under way.
    const { sent, ontap }: { sent: boolean; ontap: () => void } = $props();
</script>

<button type="button" class="copy stop" disabled={sent} onclick={ontap}>
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
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    {`${words["table.stopPlaying"]}`}
</button>
