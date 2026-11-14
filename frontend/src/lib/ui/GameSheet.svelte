<script lang="ts">
    import { gameSheetView, hasEleventhRow, type GameSheetView, type SheetSeat } from "#lib/gameSheet.ts";
    import type { GameRow } from "#lib/series.ts";
    import CardFace from "#lib/ui/CardFace.svelte";
    import PointsBar from "#lib/ui/PointsBar.svelte";
    import { words } from "#lib/words.ts";
    import type { Card } from "../../routes/(start)/tables.ts";
    import { readGameSheet } from "../../routes/(start)/tables.ts";

    // One game of the list opened in the list's own panel: its row and the way back above, then the skat, the count and
    // every seat's cards, then its tricks, which are all that scrolls.
    const { id, row, back }: { id: string; row: GameRow; back: () => void } = $props();

    let view = $state<GameSheetView | null>(null);
    let failed = $state(false);
    // The head's dot wears the colour of the seat its row names, as the dots below do: a Ramsch row carries that seat, a
    // declared game's sheet names the declarer, so that dot is plain until the sheet is read.
    const headSeat = $derived(row.subjectSeat ?? (view?.count.kind === "declared" ? view.count.declarer.seat : null));

    $effect(() => {
        let current = true;
        void readGameSheet(id, row.number).then((sheet) => {
            if (!current) return;
            failed = sheet === null;
            view = sheet === null ? null : gameSheetView(sheet);
        });
        return () => {
            current = false;
        };
    });
</script>

{#snippet dot(seat: SheetSeat, label?: string)}
    <span class={["dot", `seat-${String(seat.seat)}`]} role="img" aria-label={label ?? seat.name}>{seat.initial}</span>
{/snippet}

{#snippet skatTakers(takers: readonly SheetSeat[])}
    {#each takers as taker (taker.seat)}
        {@render dot(taker, words["table.sheetSkatTaker"]({ name: taker.name }))}
    {/each}
{/snippet}

{#snippet minis(cards: readonly Card[])}
    <span class="minis">
        {#each cards as card (`${card.suit}-${card.rank}`)}
            <span class="mini"><CardFace {card} /></span>
        {/each}
    </span>
{/snippet}

<div class="panel-body game-sheet" role="group" aria-label={words["table.sheetTitle"]({ number: String(row.number) })}>
    <div class="sheet-head">
        <button type="button" class="back" aria-label={words["table.sheetBack"]} onclick={back}>
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg
            >
        </button>
        <span class="grow">
            <span class="nr">{row.number}</span>
            <span class={["dot", headSeat !== null && `seat-${String(headSeat)}`]} aria-hidden="true"
                >{row.initial}</span
            >
            <span class="txt">
                <b>{row.name}</b>
                {#if row.line !== null}<small>{row.line}</small>{/if}
            </span>
            <span class="val">{row.value}</span>
            <span class="gain" class:minus={row.lost}>{row.gain}</span>
        </span>
    </div>
    {#if failed}
        <p class="empty" role="alert">{words["table.sheetFailed"]}</p>
    {:else if view !== null}
        {@const cards = view.cards}
        {#if cards === null}
            <p class="empty">{words["table.sheetNoCards"]}</p>
        {:else}
            <div class="skatline">
                <span class="pair">
                    <small>{words["table.sheetSkat"]}</small>
                    {@render minis(cards.skat)}
                    {#if cards.laidSkat.length === 0}{@render skatTakers(cards.skatTakers)}{/if}
                </span>
                {#if cards.putAway.length > 0}
                    <span class="puts">
                        {#each cards.putAway as put (put.by.seat)}
                            <span class="pair">
                                <small>{words["table.sheetPutAway"]}</small>
                                {#if view.count.kind === "ramsch"}{@render dot(
                                        put.by,
                                        words["table.sheetPutBy"]({ name: put.by.name }),
                                    )}{/if}
                                {@render minis(put.cards)}
                            </span>
                        {/each}
                    </span>
                {/if}
                {#if cards.laidSkat.length > 0}
                    <span class="pair">
                        <small>{words["table.sheetSkatLaid"]}</small>
                        {@render minis(cards.laidSkat)}
                        {@render skatTakers(cards.skatTakers)}
                    </span>
                {/if}
            </div>
        {/if}
        {#if view.count.kind === "declared"}
            {#if !row.nullGame}
                <PointsBar sides={view.count.sides} points={view.count.points} />
            {/if}
        {:else}
            <div class="seat-eyes">
                {#each view.count.seats as each (each.seat.seat)}
                    <span class:most={each.most}>{@render dot(each.seat)}{each.points}</span>
                {/each}
            </div>
        {/if}
        {#if cards !== null}
            <div class="held">
                {#each cards.hands as hand (hand.seat.seat)}
                    <div class="held-row">
                        {@render dot(hand.seat)}
                        <span class="minis">
                            {#each hand.cards as each (`${each.card.suit}-${each.card.rank}`)}
                                <span
                                    class={["hc", each.state]}
                                    title={each.state === "played"
                                        ? undefined
                                        : each.state === "put-away"
                                          ? words["table.sheetCardPutAway"]
                                          : words["table.sheetCardUnplayed"]}
                                    ><span class="mini"><CardFace card={each.card} /></span></span
                                >
                            {/each}
                        </span>
                    </div>
                {/each}
            </div>
            <ol class="rows tricks" class:long={hasEleventhRow(view)}>
                {#each cards.tricks as trick (trick.number)}
                    <li
                        class={["trick-row", trick.side]}
                        aria-label={words["table.sheetTrick"]({ number: String(trick.number) })}
                    >
                        <span class="nr">{trick.number}</span>
                        <span class="minis">
                            {#each trick.cards as each (`${each.card.suit}-${each.card.rank}`)}
                                <span class="trick-card">
                                    <span class="mini"><CardFace card={each.card} /></span>
                                    <span class="by" role="img" aria-label={each.by.name}>{each.by.initial}</span>
                                </span>
                            {/each}
                        </span>
                        {#if trick.taker !== null}{@render dot(trick.taker)}{/if}
                        {#if trick.points !== null}<span class="pts">{trick.points}</span>{/if}
                    </li>
                {/each}
                {#if view.end !== null}
                    <li class="trick-row ended">
                        <span class="nr">⚑</span><b>{view.end.label}</b>
                        {#if view.end.by !== null}{@render dot(view.end.by)}{/if}
                    </li>
                {/if}
            </ol>
        {/if}
    {/if}
</div>
