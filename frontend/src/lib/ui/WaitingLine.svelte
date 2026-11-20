<script lang="ts">
    import { words } from "#lib/words.ts";

    // The line a plaque shows while the table waits for players.
</script>

<span class="gives">
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    {`${words["table.waitingForPlayers"]}`}
    <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
</span>
