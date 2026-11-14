<script lang="ts">
    import { words } from "#lib/words.ts";
</script>

<span class="mark pass">
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.8"
        stroke-linecap="round"
        aria-hidden="true"
    >
        <path d="M6 6l12 12M18 6L6 18" />
    </svg>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    {`${words["table.pass"]}`}
</span>
