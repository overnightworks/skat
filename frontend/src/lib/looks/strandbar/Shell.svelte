<script lang="ts">
    import { beatAfter } from "#lib/table/scene.ts";
    import { words } from "#lib/words.ts";

    // A shell on the rim of the table: a tap on it is a reaction every page at the table shows and hears.
    const { taps, ontap }: { taps: number; ontap: () => void } = $props();
    const uid = $props.id();
</script>

<button
    type="button"
    class="decor shell"
    data-beat={beatAfter(taps)}
    aria-label={words["table.objectShell"]}
    onclick={ontap}
>
    <svg viewBox="0 0 72 62" focusable="false">
        <defs>
            <radialGradient id="shell-{uid}" cx=".5" cy=".75" r=".8">
                <stop offset="0" stop-color="#fff3ec" />
                <stop offset=".6" stop-color="#f6cfc1" />
                <stop offset="1" stop-color="#e8a99a" />
            </radialGradient>
        </defs>
        <ellipse cx="36" cy="57" rx="26" ry="4" fill="#000" opacity=".22" />
        <path
            d="M36 55C10 50 2 29 10 17C18 5 54 5 62 17C70 29 62 50 36 55Z"
            fill="url(#shell-{uid})"
            stroke="#d7a99a"
            stroke-width="1.2"
        />
        <path
            d="M36 52L14 18M36 52L22 12M36 52L31 9M36 52L41 9M36 52L50 12M36 52L58 18M36 52L10 28M36 52L62 28"
            fill="none"
            stroke="#d99a8c"
            stroke-opacity=".75"
            stroke-width="1.6"
            stroke-linecap="round"
        />
        <path d="M30 56h12l-2 4H32z" fill="#e8bfae" />
    </svg>
</button>
