<script lang="ts">
    import { words } from "#lib/words.ts";

    // The notice that a chair the person tapped was taken, and by whom.
    const { name }: { name: string } = $props();
</script>

<p class="notice" role="status">
    <span class="dot" aria-hidden="true">{name.slice(0, 1)}</span>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    <span class="label">{`${words["table.seatTaken"]}`}</span>
    <b>{name}</b>
</p>
