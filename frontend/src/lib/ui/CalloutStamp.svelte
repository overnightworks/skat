<script lang="ts">
    import type { Stamp } from "#lib/kontra.ts";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";

    const STAMP_MILLISECONDS = 2500;

    // The latest word's stamp; a new one replaces the one on the felt, and none shows again once its moment has passed.
    const { stamp }: { stamp: Stamp | null } = $props();
    let visible = $state(false);

    $effect(() => {
        visible = stamp !== null;
        if (stamp === null) return;
        const timer = setTimeout(() => (visible = false), STAMP_MILLISECONDS);
        return () => {
            clearTimeout(timer);
        };
    });
</script>

{#if stamp !== null && visible}
    {#key stamp}
        <div class="callout-spot">
            <span class="callout-ring" aria-hidden="true"></span>
            <div class="callout" class:agent={stamp.agent} role="img" aria-label={stamp.label}>
                <span class="by" aria-hidden="true">
                    {#if stamp.agent}
                        <AgentSparkle />
                    {:else}
                        {stamp.initial}
                    {/if}
                </span>
                <span aria-hidden="true">{stamp.text}</span>
            </div>
        </div>
    {/key}
{/if}
