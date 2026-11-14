<script lang="ts">
    import { onMount } from "svelte";
    import { playedCards, trickInPile, trickOnTheFelt } from "#lib/playView.ts";
    import { currentSettings } from "#lib/settings.svelte.ts";
    import { currentStage, jumpStage, lookingAt, sweepingTo } from "#lib/stage.svelte.ts";
    import type { Stamp } from "#lib/kontra.ts";
    import CalloutStamp from "#lib/ui/CalloutStamp.svelte";
    import LastTrickShown from "#lib/ui/LastTrickShown.svelte";
    import PlayedTrick from "#lib/ui/PlayedTrick.svelte";
    import type { Card, Chair, Playing } from "../../routes/(start)/tables.ts";

    // The trick on the felt as the stage shows it, not as the received table has it: a finished trick rests, glides to
    // its taker's pile and is gone, or stays until the next lead. A Kontra stamp lands above it, and the last trick lifted
    // out of its pile lies over it. A window that turns hidden shows the received table at once.
    const {
        chairs,
        playing,
        playedThisHand,
        turnSeat,
        stamp,
    }: {
        chairs: Chair[];
        playing: Playing | null;
        playedThisHand: Card[];
        turnSeat: number | null | undefined;
        stamp: Stamp | null;
    } = $props();

    const stage = $derived(currentStage());
    const mode = $derived(currentSettings().lastTrick);
    const laid = $derived(playing === null ? [] : trickOnTheFelt(chairs, playing, stage, mode));
    const lookedAt = $derived(playing === null || lookingAt() === null ? null : trickInPile(playing, stage, mode));

    onMount(() => {
        const hide = (): void => {
            if (document.hidden) jumpStage();
        };
        document.addEventListener("visibilitychange", hide);
        return () => {
            document.removeEventListener("visibilitychange", hide);
        };
    });
</script>

<CalloutStamp {stamp} aboveNearCard={laid.some(({ slot }) => slot === "near")} />
{#if playing !== null}
    <PlayedTrick {chairs} {laid} {playedThisHand} {turnSeat} sweptTo={sweepingTo()} />
{/if}
{#if lookedAt !== null}
    <LastTrickShown cards={playedCards(chairs, lookedAt)} takerSeat={lookedAt.taker_seat} />
{/if}
