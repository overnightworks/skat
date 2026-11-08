<script lang="ts">
    // Every back holds its own gradient and lattice: an id may stand only once in a page.
    const uid = $props.id();
</script>

<svg class="card-back" width="100" height="140" viewBox="0 0 100 140" aria-hidden="true">
    <defs>
        <linearGradient id="backfill-{uid}" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#22386a" />
            <stop offset="1" stop-color="#121f3d" />
        </linearGradient>
        <pattern id="lattice-{uid}" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
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
