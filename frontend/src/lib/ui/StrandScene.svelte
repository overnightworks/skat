<script lang="ts">
    import { BEACH_VIEWS, beachOf, type BeachSize } from "#lib/strandScene.ts";

    // The two blessed frames, drawn behind the table: the phone's and the desktop's; the stylesheet shows the one that
    // fits the viewport. Each holds its own gradients, so no id stands twice in the page.
    const uid = $props.id();
    const SIZES: readonly BeachSize[] = ["phone", "desktop"];
</script>

<div class="strand-scene" aria-hidden="true">
    {#each SIZES as size (size)}
        {@const beach = beachOf(size)}
        {@const view = BEACH_VIEWS[size]}
        <svg
            class="beach beach-{size}"
            viewBox="0 0 {view.width} {view.height}"
            preserveAspectRatio="xMidYMid slice"
            focusable="false"
        >
            <defs>
                <linearGradient id="sky-{size}-{uid}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stop-color="#11173f" />
                    <stop offset=".42" stop-color="#3c2f72" />
                    <stop offset=".74" stop-color="#b6507a" />
                    <stop offset="1" stop-color="#ff9f68" />
                </linearGradient>
                <linearGradient id="water-{size}-{uid}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stop-color="#c8798e" />
                    <stop offset=".22" stop-color="#4d6f98" />
                    <stop offset=".7" stop-color="#1d5273" />
                    <stop offset="1" stop-color="#103c58" />
                </linearGradient>
                <linearGradient id="sand-{size}-{uid}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stop-color="#8a6a54" />
                    <stop offset=".08" stop-color="#b68f68" />
                    <stop offset=".5" stop-color="#cba57a" />
                    <stop offset="1" stop-color="#a98259" />
                </linearGradient>
                <radialGradient id="glow-{size}-{uid}" cx=".5" cy=".5" r=".5">
                    <stop offset="0" stop-color="#ffd8a0" stop-opacity=".75" />
                    <stop offset=".4" stop-color="#ff9f68" stop-opacity=".3" />
                    <stop offset="1" stop-color="#ff9f68" stop-opacity="0" />
                </radialGradient>
                <radialGradient id="bulb-{size}-{uid}" cx=".5" cy=".5" r=".5">
                    <stop offset="0" stop-color="#ffd98a" stop-opacity=".85" />
                    <stop offset="1" stop-color="#ffd98a" stop-opacity="0" />
                </radialGradient>
                <radialGradient id="shade-{size}-{uid}" cx=".5" cy=".42" r=".75">
                    <stop offset=".55" stop-color="#1a0f24" stop-opacity="0" />
                    <stop offset="1" stop-color="#1a0f24" stop-opacity=".55" />
                </radialGradient>
                <linearGradient id="foam-{size}-{uid}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stop-color="#fff" stop-opacity=".5" />
                    <stop offset="1" stop-color="#fff" stop-opacity="0" />
                </linearGradient>
            </defs>
            <rect width={beach.width} height={beach.horizon + 1} fill="url(#sky-{size}-{uid})" />
            {#each beach.stars as star, index (index)}
                <circle cx={star.x} cy={star.y} r={star.r} fill="#fff" opacity={star.opacity} />
            {/each}
            <ellipse
                cx={beach.width * 0.3}
                cy={beach.horizon * 0.62}
                rx={beach.width * 0.16}
                ry={size === "desktop" ? 7 : 4}
                fill="#ffb4a0"
                opacity=".28"
            />
            <ellipse
                cx={beach.width * 0.78}
                cy={beach.horizon * 0.5}
                rx={beach.width * 0.12}
                ry={size === "desktop" ? 6 : 3.5}
                fill="#ffc9a8"
                opacity=".25"
            />
            <circle cx={beach.sunX} cy={beach.horizon} r={beach.glowRadius} fill="url(#glow-{size}-{uid})" />
            <path
                d="M{beach.sunX -
                    beach.sunRadius} {beach.horizon}A{beach.sunRadius} {beach.sunRadius} 0 0 1 {beach.sunX +
                    beach.sunRadius} {beach.horizon}Z"
                fill="#fff0c2"
            />
            <rect
                y={beach.horizon}
                width={beach.width}
                height={beach.shore - beach.horizon}
                fill="url(#water-{size}-{uid})"
            />
            {#each beach.sunPath as bar, index (index)}
                <rect
                    x={bar.x}
                    y={bar.y}
                    width={bar.width}
                    height={bar.height}
                    rx="1.5"
                    fill="#ffd9a0"
                    opacity={bar.opacity}
                />
            {/each}
            {#each beach.seaLines as line, index (index)}
                <path d={line.d} fill="none" stroke="#fff" stroke-opacity={line.opacity} stroke-width="1.4" />
            {/each}
            <rect
                y={beach.shore}
                width={beach.width}
                height={beach.height - beach.shore}
                fill="url(#sand-{size}-{uid})"
            />
            {#each beach.speckle as grain, index (index)}
                <circle
                    cx={grain.x}
                    cy={grain.y}
                    r={grain.r}
                    fill={grain.light ? "#fff3d6" : "#7a5a38"}
                    opacity={grain.opacity}
                />
            {/each}
            <!-- The waves roll in and out; the stylesheet moves them only while the motion set allows it. -->
            <g class="surf">
                <path
                    class="surf-foam"
                    d="{beach.foam[0]?.d}V{beach.shore + beach.foamDepth}H0Z"
                    fill="url(#foam-{size}-{uid})"
                />
                {#each beach.foam.slice(1) as line, index (index)}
                    <path
                        class="surf-line"
                        d={line.d}
                        fill="none"
                        stroke="#fff"
                        stroke-opacity={line.opacity}
                        stroke-width={line.width}
                        stroke-linecap="round"
                    />
                {/each}
            </g>
            {#each beach.bulbs as bulb, index (index)}
                <circle cx={bulb.x} cy={bulb.y} r="14" fill="url(#bulb-{size}-{uid})" />
                <circle cx={bulb.x} cy={bulb.y} r="3.6" fill="#fff1c9" />
            {/each}
            <rect width={beach.width} height={beach.height} fill="url(#shade-{size}-{uid})" />
        </svg>
    {/each}
</div>
