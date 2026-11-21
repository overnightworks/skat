<script lang="ts">
    import { words } from "#lib/words.ts";

    /** The call app's fixed start link for this table. */
    const { address }: { address: string } = $props();
</script>

<!-- eslint-disable svelte/no-navigation-without-resolve -- the address leaves this app for the call app -->
<a
    class="call-key"
    href={address}
    target="_blank"
    rel="noopener"
    title={words["table.call"]}
    aria-label={words["table.call"]}
>
    <span class="call-face">
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <rect x="3" y="6.5" width="12" height="11" rx="2.5" />
            <path d="m15 11 6-3.5v9L15 13z" />
        </svg>
        <span class="call-word">{words["table.call"]}</span>
    </span>
</a>
<!-- eslint-enable svelte/no-navigation-without-resolve -->
