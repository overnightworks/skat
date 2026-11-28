<script lang="ts">
    import LookSwitch from "#lib/table/LookSwitch.svelte";
    import type { SurfaceScene } from "#lib/table/scene.ts";
    import { words } from "#lib/words.ts";
    import type { SurfaceLook } from "../look.ts";
    import Chair from "./Chair.svelte";
    import Lamp from "./Lamp.svelte";

    // Unter der Lampe: a pub table at night seen from a little above, under a hanging lamp. Only the felt is tilted;
    // everything a person reads stands upright. The room is measured in one unit that grows with the screen.
    const { look, scene }: { look: SurfaceLook; scene: SurfaceScene } = $props();
</script>

<main class="lampe" data-look="lampe" aria-label={scene.name}>
    <div class="room" aria-hidden="true">
        <div class="wall"></div>
        <div class="cone"></div>
    </div>
    <div class="stage">
        <Lamp />
        <div class="plane-wrap" aria-hidden="true">
            <div class="plane">
                <div class="wood"></div>
                <div class="felt"></div>
            </div>
        </div>
        <header class="top">
            <div class="badge">
                <svg viewBox="0 0 64 64" focusable="false" aria-hidden="true">
                    <path d="M32 2v14" fill="none" stroke="currentColor" stroke-width="2" />
                    <path d="M14 34c0-10 8-18 18-18s18 8 18 18z" fill="currentColor" />
                    <ellipse class="badge-bulb" cx="32" cy="36" rx="6" ry="3" />
                    <path class="badge-light" d="M20 38L6 62h52L44 38z" />
                </svg>
                <b>{words[look.name]}</b>
            </div>
            <LookSwitch />
        </header>
        {#each scene.chairs as chair (chair.seat)}
            <Chair {chair} />
        {/each}
        {#if scene.notice !== null}
            <p class="notice" aria-hidden="true">{scene.notice}</p>
        {/if}
    </div>
</main>
