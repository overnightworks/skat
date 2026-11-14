<script lang="ts">
    import { words } from "#lib/words.ts";
</script>

<span class="mark dealer" title={words["table.dealer"]}>
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path
            d="M3 7h3c4.5 0 6.5 10 11 10h3.5M3 17h3c1.7 0 3-1.4 4.1-3.4M13.9 10.4C15 8.4 16.3 7 18 7h2.5M18 4l3 3-3 3M18 14l3 3-3 3"
        />
    </svg>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    {`${words["table.dealer"]}`}
</span>
