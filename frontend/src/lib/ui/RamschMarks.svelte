<script lang="ts">
    import type { RamschMarks } from "#lib/ramschView.ts";
    import { words } from "#lib/words.ts";
    import AgentSparkle from "./AgentSparkle.svelte";

    const { marks, initial }: { marks: RamschMarks; initial: string } = $props();
</script>

{#if marks.thinks}
    <span class="mark think">
        <AgentSparkle />
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
        {`${words["table.thinks"]}`}
    </span>
{/if}
{#if marks.pushed}
    <span class="bubble word">
        <span class="dot" aria-hidden="true">{initial}</span>
        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
        {`${words["table.push"]}`}
    </span>
{/if}
