<!-- The hanging lamp over the table; its cord runs up out of the room. -->
<div class="lamp" aria-hidden="true">
    <svg viewBox="0 0 240 150" focusable="false">
        <defs>
            <linearGradient id="lampe-shade" x1="0" y1="0" x2="0" y2="1">
                <stop class="shade-top" offset="0" />
                <stop class="shade-bottom" offset="1" />
            </linearGradient>
            <radialGradient id="lampe-bulb" cx="50%" cy="0%" r="70%">
                <stop class="bulb-core" offset="0" />
                <stop class="bulb-glow" offset=".5" />
                <stop class="bulb-edge" offset="1" />
            </radialGradient>
        </defs>
        <rect class="fitting" x="108" y="30" width="24" height="14" rx="4" />
        <path d="M26 118C34 70 76 42 120 42C164 42 206 70 214 118Z" fill="url(#lampe-shade)" />
        <path class="sheen" d="M44 100C58 70 88 52 120 52" fill="none" stroke-width="5" stroke-linecap="round" />
        <ellipse class="fitting" cx="120" cy="118" rx="94" ry="11" />
        <ellipse class="rim" cx="120" cy="120" rx="88" ry="8" />
        <ellipse cx="120" cy="126" rx="70" ry="22" fill="url(#lampe-bulb)" />
    </svg>
</div>
