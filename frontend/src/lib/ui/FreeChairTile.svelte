<script lang="ts">
    import { words } from "#lib/words.ts";

    const { ontap }: { ontap: () => void } = $props();
</script>

<button type="button" class="tile empty free" aria-label={words["table.sitDown"]} onclick={ontap}>
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.2"
        stroke-linecap="round"
        aria-hidden="true"
    >
        <path d="M12 5v14M5 12h14" />
    </svg>
</button>
