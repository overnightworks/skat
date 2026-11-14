<script lang="ts">
    import { tableStyle } from "#lib/tableStyle.svelte.ts";

    // Every back holds its own gradient and lattice: an id may stand only once in a page.
    const uid = $props.id();
</script>

{#snippet dusk()}
    <rect x="6" y="6" width="88" height="64" fill="url(#dusk-{uid})" />
    <circle cx="26" cy="20" r=".9" fill="#fff" />
    <circle cx="72" cy="15" r="1.1" fill="#fff" />
    <circle cx="48" cy="28" r=".8" fill="#fff" opacity=".8" />
    <circle cx="84" cy="32" r=".8" fill="#fff" opacity=".8" />
    <circle cx="16" cy="36" r=".7" fill="#fff" opacity=".7" />
    <g fill="#ffd9b0" opacity=".55">
        <rect x="62" y="52" width="26" height="2.2" rx="1.1" />
        <rect x="68" y="58" width="18" height="2.2" rx="1.1" />
        <rect x="12" y="46" width="22" height="2.2" rx="1.1" />
    </g>
    <circle cx="50" cy="70" r="17" fill="url(#sun-{uid})" />
    <path d="M21 70C21 62 22 56 25 50" fill="none" stroke="#14213f" stroke-width="2.2" stroke-linecap="round" />
    <g fill="#14213f" transform="translate(25 50)">
        <path d="M0 0C-3-7-12-9-18-5C-11-5-5-4 0 0Z" />
        <path d="M0 0C-1-8-6-14-13-14C-7-11-3-6 0 0Z" />
        <path d="M0 0C4-7 11-9 17-5C10-5 4-4 0 0Z" />
        <path d="M0 0C3-8 8-13 15-12C9-10 4-6 0 0Z" />
        <path d="M0 0C-6 1-12 6-13 12C-8 7-4 3 0 0Z" />
        <path d="M0 0C5 1 11 5 13 11C8 6 4 3 0 0Z" />
    </g>
{/snippet}

{#if tableStyle() === "strandbar"}
    <svg class="card-back" width="100" height="140" viewBox="0 0 100 140" aria-hidden="true">
        <defs>
            <linearGradient id="dusk-{uid}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#14305f" />
                <stop offset=".55" stop-color="#4a4f8f" />
                <stop offset=".85" stop-color="#e9806a" />
                <stop offset="1" stop-color="#ffc47e" />
            </linearGradient>
            <radialGradient id="sun-{uid}" cx=".5" cy=".5" r=".5">
                <stop offset="0" stop-color="#fff6d0" />
                <stop offset="1" stop-color="#ffc47e" />
            </radialGradient>
            <clipPath id="inner-{uid}"><rect x="6" y="6" width="88" height="128" rx="4" /></clipPath>
            <clipPath id="upper-{uid}"><rect x="0" y="0" width="100" height="70" /></clipPath>
        </defs>
        <rect x=".75" y=".75" width="98.5" height="138.5" rx="7" fill="#fbf8f0" stroke="#cfc6b1" stroke-width="1.5" />
        <g clip-path="url(#inner-{uid})">
            <!-- One half of a dusk sea, turned half a round for the other, so the back reads the same either way up. -->
            <g clip-path="url(#upper-{uid})">{@render dusk()}</g>
            <g clip-path="url(#upper-{uid})" transform="rotate(180 50 70)">{@render dusk()}</g>
            <path d="M6 70H94" stroke="#ffe3b0" stroke-width="1.3" />
        </g>
        <rect
            x="10.5"
            y="10.5"
            width="79"
            height="119"
            rx="2.5"
            fill="none"
            stroke="#f4dfae"
            stroke-opacity=".85"
            stroke-width="1.3"
        />
    </svg>
{:else}
    <svg class="card-back" width="100" height="140" viewBox="0 0 100 140" aria-hidden="true">
        <defs>
            <linearGradient id="backfill-{uid}" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#22386a" />
                <stop offset="1" stop-color="#121f3d" />
            </linearGradient>
            <pattern
                id="lattice-{uid}"
                width="9"
                height="9"
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
            >
                <path d="M0 0H9M0 0V9" stroke="#d6b46a" stroke-opacity=".38" stroke-width="1.1" />
                <circle cx="4.5" cy="4.5" r="1" fill="#d6b46a" fill-opacity=".45" />
            </pattern>
        </defs>
        <rect x=".75" y=".75" width="98.5" height="138.5" rx="7" fill="#fbf8f0" stroke="#cfc6b1" stroke-width="1.5" />
        <rect x="6" y="6" width="88" height="128" rx="4" fill="url(#backfill-{uid})" />
        <rect x="6" y="6" width="88" height="128" rx="4" fill="url(#lattice-{uid})" />
        <rect
            x="10.5"
            y="10.5"
            width="79"
            height="119"
            rx="2.5"
            fill="none"
            stroke="#d6b46a"
            stroke-opacity=".75"
            stroke-width="1.4"
        />
        <path d="M50 46L72 70L50 94L28 70Z" fill="#1a2c55" stroke="#d6b46a" stroke-width="1.6" />
        <path d="M50 56L62 70L50 84L38 70Z" fill="#d6b46a" fill-opacity=".85" />
    </svg>
{/if}
