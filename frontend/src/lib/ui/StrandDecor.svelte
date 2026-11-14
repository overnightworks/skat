<script lang="ts">
    import { tableStyle } from "#lib/tableStyle.svelte.ts";

    // A cocktail on a straw coaster and a shell on the rim of the table: they sit at the rim's edge, clear of every card
    // and key, and the stylesheet places them.
    const uid = $props.id();
</script>

{#if tableStyle() === "strandbar"}
    <span class="decor cocktail" aria-hidden="true">
        <svg viewBox="0 0 64 100" focusable="false">
            <defs>
                <linearGradient id="drink-{uid}" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" stop-color="#ff5d73" />
                    <stop offset="1" stop-color="#ffa23a" />
                </linearGradient>
            </defs>
            <ellipse cx="32" cy="94" rx="28" ry="5.5" fill="#d9b66e" />
            <ellipse cx="32" cy="93" rx="22" ry="3.4" fill="none" stroke="#a9843f" stroke-width="1" />
            <path d="M30.5 54h3v36h-3z" fill="#e4f2f2" opacity=".85" />
            <ellipse cx="32" cy="90" rx="13" ry="3" fill="#e4f2f2" opacity=".9" />
            <path
                d="M5 16h54L36 56h-8z"
                fill="#ffffff"
                fill-opacity=".2"
                stroke="#f0fbfb"
                stroke-width="1.6"
                stroke-linejoin="round"
            />
            <path d="M9.5 21h45L35.5 52h-7z" fill="url(#drink-{uid})" />
            <path d="M13 23h14" stroke="#fff" stroke-opacity=".6" stroke-width="2" stroke-linecap="round" />
            <path d="M40 40L52 4" stroke="#e5484d" stroke-width="3" stroke-linecap="round" />
            <path d="M42.5 33L45 26M47 19.5L49.5 12" stroke="#fff" stroke-width="3" stroke-linecap="round" />
            <circle cx="53" cy="17" r="9" fill="#ffae2b" />
            <circle cx="53" cy="17" r="6.6" fill="#ffd36a" />
            <path
                d="M53 10.4v13.2M46.4 17h13.2M48.3 12.3l9.4 9.4M57.7 12.3l-9.4 9.4"
                stroke="#ffae2b"
                stroke-width=".8"
            />
            <path d="M14 22L16 3" stroke="#6d4a2b" stroke-width="1.4" stroke-linecap="round" />
            <path d="M7 7Q16-5 25 7Q21 4.5 16 5.5Q11 4.5 7 7Z" fill="#2fb7a6" />
        </svg>
    </span>
    <span class="decor shell" aria-hidden="true">
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
    </span>
{/if}
