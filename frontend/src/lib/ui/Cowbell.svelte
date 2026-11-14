<script lang="ts">
    import { words } from "#lib/words.ts";
</script>

<!-- The cowbell that swings over the chair the table waits for: its strap, its brass body, its mouth with the clapper. -->
<span class="cowbell" role="img" aria-label={words["table.nudged"]}>
    <svg viewBox="0 0 48 66" aria-hidden="true">
        <path d="M17 15V7a7 7 0 0 1 14 0v8" fill="none" stroke="#6b4a2a" stroke-width="4" stroke-linecap="round" />
        <path d="M13 15h22l8 38H5z" class="body" stroke-width="1.6" stroke-linejoin="round" />
        <path d="M17 18h6l-3 32h-8z" class="shine" />
        <ellipse cx="24" cy="53" rx="19" ry="4.6" fill="#2d2108" />
        <rect x="21" y="52" width="6" height="11" rx="3" fill="#7a5a22" />
    </svg>
    <i class="ring left"></i>
    <i class="ring right"></i>
</span>
