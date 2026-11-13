<script lang="ts">
    import type { SeatNotice } from "#lib/openChair.ts";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";

    const { notice }: { notice: SeatNotice } = $props();
</script>

<p class="notice" role="status">
    {#each notice.initials as initial, index (index)}
        {#if initial === null}
            <span class="dot agent" aria-hidden="true">
                <AgentSparkle />
            </span>
        {:else}
            <span class="dot" aria-hidden="true">{initial}</span>
        {/if}
    {/each}
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {notice.text} compiles to a `?? ""` branch no sentence can take -->
    <span class="label">{`${notice.text}`}</span>
</p>
