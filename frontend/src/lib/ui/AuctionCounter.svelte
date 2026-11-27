<script lang="ts">
    import { untrack } from "svelte";
    import type { Action } from "svelte/action";
    import type { Attachment } from "svelte/attachments";
    import { duelOf } from "#lib/auctionMarks.ts";
    import { pairTurned, rollsTo, type BidSaid } from "#lib/cues.ts";
    import { motionOnStage } from "#lib/stage.svelte.ts";
    import { duelTimeline, rollTimeline } from "#lib/takt/bids.ts";
    import { fade, letRest, move } from "#lib/takt/player.ts";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";
    import { words } from "#lib/words.ts";
    import type { Auction, Chair } from "../../routes/(start)/tables.ts";

    // The brass counter of a running auction: the bid that stands on its drums, which are empty before the first bid,
    // and under it who bids against whom. The drums roll to a bid this page saw said, and a pair fades in after a
    // „Weg“ this page saw said; a table shown as it stands, as after a dropped connection, moves nothing. `said` holds
    // the bids of the latest update that brought any.
    const { auction, chairs, said }: { auction: Auction; chairs: readonly Chair[]; said: readonly BidSaid[] } =
        $props();

    const LEAST_DRUMS = 2;
    const digits = $derived(
        String(auction.standing ?? "")
            .padStart(LEAST_DRUMS, " ")
            .split(""),
    );
    const duel = $derived(duelOf(auction, chairs));
    const bidSeen = $derived(rollsTo(said, auction.standing));

    // The stylesheet draws the digit a drum showed before right above the one it shows, so the roll carries it out.
    const rolls: Action<HTMLElement, { digit: string; place: number; seen: boolean }> = (reel, shown) => {
        let was = shown.digit;
        return {
            update({ digit, place, seen }) {
                if (digit === was) return;
                reel.dataset.was = was;
                was = digit;
                const bids = untrack(motionOnStage)?.bids;
                if (!seen || bids === undefined) return;
                const { tracks, seconds } = rollTimeline(bids, { height: reel.getBoundingClientRect().height, place });
                letRest(reel);
                move(reel, tracks.reel, seconds);
            },
        };
    };

    const nameOf = (chair: Chair): string => (chair.is_mine ? words["table.sideYou"] : String(chair.occupant_name));

    let pairShown: string | undefined;
    const appearsAs =
        (pair: string): Attachment<HTMLElement> =>
        (line) => {
            const bids = untrack(motionOnStage)?.bids;
            if (pairShown !== undefined && bids !== undefined && untrack(() => pairTurned(said))) {
                const { tracks, seconds } = duelTimeline(bids);
                fade(line, tracks.line, seconds);
            }
            pairShown = pair;
        };
</script>

{#snippet word(text: string | number)}{text}{/snippet}

{#snippet dot(chair: Chair)}
    <span class="dot" class:agent={chair.occupant_kind === "agent"} aria-hidden="true">
        {#if chair.occupant_kind === "agent"}
            <AgentSparkle />
        {:else}
            {@render word(String(chair.occupant_name).slice(0, 1))}
        {/if}
    </span>
{/snippet}

{#snippet name(chair: Chair)}
    <b aria-hidden="true">{@render word(nameOf(chair))}</b>
{/snippet}

<div class="bid-counter">
    <div class="counter">
        <span class="word">{@render word(words["table.bidding"])}</span>
        <span class="sr-only">{@render word(auction.standing ?? "")}</span>
        <span class="drums" aria-hidden="true">
            {#each digits as digit, index (digits.length - index)}
                <span class="drum">
                    <i class="reel" use:rolls={{ digit, place: digits.length - 1 - index, seen: bidSeen }}>{digit}</i>
                </span>
            {/each}
        </span>
    </div>
    {#if duel !== null}
        {@const pair = `${String(duel.bidder.seat)}-${String(duel.listener.seat)}`}
        {#key pair}
            <div class="duel" {@attach appearsAs(pair)}>
                <span class="sr-only">
                    {@render word(
                        words["table.duel"]({ bidder: nameOf(duel.bidder), listener: nameOf(duel.listener) }),
                    )}
                </span>
                {@render dot(duel.bidder)}
                {@render name(duel.bidder)}
                <span class="to" aria-hidden="true">
                    <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.4"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    >
                        <path d="M5 12h14M13 6l6 6-6 6" />
                    </svg>
                </span>
                {@render name(duel.listener)}
                {@render dot(duel.listener)}
            </div>
        {/key}
    {/if}
</div>
