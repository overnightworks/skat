<script lang="ts">
    import { onMount } from "svelte";
    import { playedCards, trickInPile, trickOnTheFelt } from "#lib/playView.ts";
    import { currentSettings } from "#lib/settings.svelte.ts";
    import { currentStage, jumpStage, lookingAt, sweepingTo, takingCard } from "#lib/stage.svelte.ts";
    import type { Stamp } from "#lib/kontra.ts";
    import CalloutStamp from "#lib/ui/CalloutStamp.svelte";
    import LastTrickShown from "#lib/ui/LastTrickShown.svelte";
    import { seedOf } from "#lib/takt/seed.ts";
    import PlayedTrick from "#lib/ui/PlayedTrick.svelte";
    import type { Card, Playing, Table } from "../../routes/(start)/tables.ts";

    // The trick on the felt as the stage shows it, not as the received table has it: a finished trick rests, lifts the
    // card that took it in a brass rim, glides to its taker's pile and is gone, or stays until the next lead. A Kontra
    // stamp lands above it, and the last trick lifted out of its pile lies over it. The card that took the last trick of
    // a declared hand also carries the seal of the declarer's outcome, until the result rises. A window that turns
    // hidden shows the received table at once.
    const {
        table,
        playing,
        playedThisHand,
        turnSeat,
        stamp,
    }: {
        table: Table;
        playing: Playing | null;
        playedThisHand: Card[];
        turnSeat: number | null | undefined;
        stamp: Stamp | null;
    } = $props();

    const chairs = $derived(table.chairs);
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
    <PlayedTrick
        {chairs}
        {laid}
        {playedThisHand}
        seed={seedOf(table)}
        {turnSeat}
        sweptTo={sweepingTo()}
        took={takingCard()}
    />
{/if}
{#if lookedAt !== null}
    <LastTrickShown cards={playedCards(chairs, lookedAt)} takerSeat={lookedAt.taker_seat} />
{/if}
