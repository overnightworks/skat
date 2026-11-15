<script lang="ts">
    import type { TableStyle } from "../../routes/(start)/tables.ts";

    // The small picture on a style's tile, as the blessed strand-choose scene draws it: the table seen from above with its
    // two card backs and the side chips in Klassik, the beach with its bar table and two coasters in Strandbar.
    const { style }: { style: TableStyle } = $props();
</script>

<svg class="style-preview" viewBox="0 0 120 76" aria-hidden="true">
    {#if style === "klassik"}
        <rect width="120" height="76" fill="#1b130d" />
        <rect x="8" y="10" width="104" height="56" rx="28" fill="#7a4c2a" />
        <rect x="12" y="14" width="96" height="48" rx="24" fill="#1d7a55" />
        <rect
            x="48"
            y="26"
            width="13"
            height="19"
            rx="2"
            fill="#22386a"
            stroke="#d6b46a"
            stroke-width=".8"
            transform="rotate(-8 54 36)"
        />
        <rect
            x="60"
            y="26"
            width="13"
            height="19"
            rx="2"
            fill="#22386a"
            stroke="#d6b46a"
            stroke-width=".8"
            transform="rotate(7 66 36)"
        />
        <rect x="2" y="30" width="16" height="14" rx="3" fill="#3a3a40" />
        <rect x="102" y="30" width="16" height="14" rx="3" fill="#2a3b5e" />
    {:else}
        <defs>
            <linearGradient id="style-preview-sky" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#2a2760" />
                <stop offset="1" stop-color="#f08a63" />
            </linearGradient>
        </defs>
        <rect width="120" height="76" fill="#cba57a" />
        <rect width="120" height="24" fill="url(#style-preview-sky)" />
        <circle cx="84" cy="24" r="7" fill="#fff0c2" />
        <rect y="24" width="120" height="12" fill="#2f6285" />
        <path
            d="M0 36Q8 33 16 36T32 36T48 36T64 36T80 36T96 36T112 36T128 36"
            fill="none"
            stroke="#fff"
            stroke-width="1.6"
            opacity=".85"
        />
        <circle cx="60" cy="48" r="26" fill="#e8cf9f" />
        <circle cx="60" cy="48" r="22" fill="#d7b27c" />
        <circle cx="60" cy="48" r="20" fill="none" stroke="#fff3d0" stroke-opacity=".6" stroke-width="1" />
        <rect
            x="50"
            y="38"
            width="12"
            height="17"
            rx="2"
            fill="#26427a"
            stroke="#f4dfae"
            stroke-width=".8"
            transform="rotate(-8 56 46)"
        />
        <rect
            x="59"
            y="38"
            width="12"
            height="17"
            rx="2"
            fill="#26427a"
            stroke="#f4dfae"
            stroke-width=".8"
            transform="rotate(7 65 46)"
        />
        <circle cx="14" cy="48" r="8" fill="#e6c88c" />
        <circle cx="106" cy="48" r="8" fill="#e6c88c" />
    {/if}
</svg>
