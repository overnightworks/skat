<script lang="ts">
    import type { SeatNotice } from "#lib/openChair.ts";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";

    const { notice }: { notice: SeatNotice } = $props();
</script>

<p class="notice seat" role="status">
    {#if notice.initial === null}
        <span class="dot agent" aria-hidden="true">
            <AgentSparkle />
        </span>
    {:else}
        <span class="dot" aria-hidden="true">{notice.initial}</span>
    {/if}
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {notice.text} compiles to a `?? ""` branch no sentence can take -->
    <span class="label">{`${notice.text}`}</span>
</p>
