<script lang="ts">
    import { words } from "#lib/words.ts";

    let { won }: { won: boolean } = $props();
</script>

<span class="mark declarer" class:won>
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2.5l2.9 6.2 6.8.8-5 4.7 1.3 6.7L12 17.5 6 20.9l1.3-6.7-5-4.7 6.8-.8z" />
    </svg>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    {`${words["table.plays"]}`}
</span>
