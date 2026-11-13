<script lang="ts">
    import { words } from "#lib/words.ts";

    const { count }: { count: number } = $props();
</script>

<span class="count-tag" title={words["table.cardCount"]}>
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <rect x="3" y="7" width="11" height="14.5" rx="2" />
        <path d="M8 7V4.5A1.5 1.5 0 0 1 9.5 3h10A1.5 1.5 0 0 1 21 4.5v12a1.5 1.5 0 0 1-1.5 1.5H14" />
    </svg>
    <span>{count}</span>
</span>
