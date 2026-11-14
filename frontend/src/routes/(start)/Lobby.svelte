<script lang="ts">
    import { goto } from "$app/navigation";
    import { resolve } from "$app/paths";
    import { AiMark } from "overnightworks-design";
    import { onMount, type Snippet } from "svelte";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";
    import LockIcon from "#lib/ui/LockIcon.svelte";
    import RuleMark from "#lib/ui/RuleMark.svelte";
    import { words } from "#lib/words.ts";
    import {
        cardOf,
        openCardOf,
        watchLobby,
        type Card,
        type ChipKind,
        type LobbyTable,
        type OpenTable,
        type SeatCard,
    } from "./lobby.ts";
    import { sitDown } from "./tables.ts";

    const COUNTDOWN_MILLISECONDS = 1_000;
    const WIDEST_ROW = 3;
    const chipIcons: Record<ChipKind, Snippet> = {
        turn: turnIcon,
        ends: endsIcon,
        gameWaits: endsIcon,
        paused: endsIcon,
        seriesOver: trophyIcon,
        result: trophyIcon,
    };

    // Whether the lobby has anything to show, for the page that makes room for it.
    let { shown = $bindable(false) }: { shown: boolean } = $props();

    // A list is null until the stream has sent it, so the lobby says nothing before it knows.
    let tables = $state<LobbyTable[] | null>(null);
    let openTables = $state<OpenTable[] | null>(null);
    let connected = $state(true);
    // When each list came, by the page's stopwatch: a list's holds count down from there, and a newer list of the other
    // kind does not restart them.
    let mineReceivedAt = $state(0);
    let openReceivedAt = $state(0);
    let now = $state(Date.now());
    let stopwatch = $state(0);
    let sitting = $state(false);
    let sitFailed = $state(false);

    const mine: Card[] = $derived((tables ?? []).map((table) => cardOf(table, now, stopwatch - mineReceivedAt)));
    const open: Card[] | null = $derived(
        openTables?.map((table) => openCardOf(table, stopwatch - openReceivedAt)) ?? null,
    );
    // Both sections share the row's width, so the longer list sets the columns.
    const columns = $derived(Math.min(Math.max(mine.length, open?.length ?? 0, 1), WIDEST_ROW));

    $effect(() => {
        shown = mine.length > 0 || open !== null;
    });

    // The page counts a hold down with its own stopwatch, which no clock change moves; a new list replaces the count.
    function tickClocks(): number {
        stopwatch = performance.now();
        now = Date.now();
        return stopwatch;
    }

    // One tap on a free chair seats the person, and the table opens once the server has seated them.
    async function sit(card: Card, seat: number): Promise<void> {
        sitting = true;
        sitFailed = false;
        const outcome = await sitDown(card.id, seat, crypto.randomUUID());
        sitting = false;
        if (outcome.kind === "table") await goto(resolve("/(start)/t/[id]", { id: card.id }));
        else sitFailed = true;
    }

    onMount(() => {
        const stop = watchLobby(
            (list) => {
                mineReceivedAt = tickClocks();
                tables = list;
            },
            (list) => {
                openReceivedAt = tickClocks();
                openTables = list;
            },
            (line) => {
                connected = line;
            },
        );
        const tick = setInterval(tickClocks, COUNTDOWN_MILLISECONDS);
        return () => {
            clearInterval(tick);
            stop();
        };
    });
</script>

{#snippet turnIcon()}
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5l11 7-11 7z" /></svg>
{/snippet}

{#snippet endsIcon()}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
    </svg>
{/snippet}

{#snippet trophyIcon()}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path d="M7 4h10v5a5 5 0 0 1-10 0zM7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3M12 14v4M8 20h8" />
    </svg>
{/snippet}

{#snippet plateOf(seat: SeatCard)}
    <span class="lobby-plate">
        <b
            >{seat.name}{#if seat.agent}<AiMark />{/if}</b
        >
        {#if seat.hold !== null}
            <small title={seat.hold.title}>{seat.hold.note}</small>
        {/if}
    </span>
{/snippet}

{#snippet seatsOf(card: Card)}
    <div class="lobby-row">
        <div class="lobby-table"><div class="lobby-felt"></div></div>
        {#each card.seats as seat (seat.seat)}
            <div class="lobby-seat" class:turn={seat.turn} class:away={seat.away}>
                {#if seat.sitLabel !== null}
                    <button
                        type="button"
                        class="lobby-chair lobby-sit"
                        aria-label={seat.sitLabel}
                        disabled={sitting}
                        onclick={() => {
                            void sit(card, seat.seat);
                        }}
                    >
                        <span class="tile free">
                            <span class="plus">
                                <svg
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    stroke-width="2.4"
                                    stroke-linecap="round"
                                    aria-hidden="true"
                                >
                                    <path d="M12 5v14M5 12h14" />
                                </svg>
                            </span>
                        </span>
                        {@render plateOf(seat)}
                    </button>
                {:else}
                    <div class="lobby-chair">
                        <span class="tile" class:agent={seat.agent} class:free={seat.free}>
                            {#if seat.agent}
                                <span class="orb" aria-hidden="true"><AgentSparkle /></span>
                            {:else}
                                <span class="initial" aria-hidden="true">{seat.initial}</span>
                            {/if}
                        </span>
                    </div>
                {/if}
                {#if seat.turn}
                    <span class="lobby-mark turn" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5l11 7-11 7z" /></svg>
                    </span>
                {/if}
                {#if seat.away}
                    <span class="lobby-mark away" title={words["lobby.seatAway"]}>
                        <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            aria-hidden="true"
                        >
                            <path d="M19.5 14.6A7.8 7.8 0 1 1 9.4 4.5a6.3 6.3 0 0 0 10.1 10.1z" />
                        </svg>
                    </span>
                {/if}
                {#if seat.sitLabel === null}
                    {@render plateOf(seat)}
                {/if}
                {#if seat.total !== null}
                    <span class="lobby-coaster">{seat.total}</span>
                {/if}
            </div>
        {/each}
    </div>
{/snippet}

{#snippet cardOfTable(card: Card)}
    <header>
        <h3>
            {card.title}{#if card.private}<span
                    class="lock"
                    role="img"
                    aria-label={words["lobby.private"]}
                    title={words["lobby.private"]}><LockIcon /></span
                >{/if}
        </h3>
        <span class="side">
            {#if card.progress !== null}
                <span class="chip official">{card.progress}</span>
            {/if}
            {#if card.watchers !== null}
                <span
                    class="watch"
                    class:none={card.watchers === 0}
                    role="group"
                    aria-label={words["table.watchers"]}
                    title={words["table.watchers"]}
                >
                    <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        aria-hidden="true"
                    >
                        <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
                        <circle cx="12" cy="12" r="3" />
                    </svg>
                    <span>{card.watchers}</span>
                </span>
            {/if}
        </span>
    </header>
    {@render seatsOf(card)}
    {#if card.rules.length > 0 || card.chips.length > 0}
        <div class="lobby-chips">
            {#each card.rules as rule (rule.id)}
                <span class="chip" class:official={rule.id === "official"}>
                    <RuleMark id={rule.id} />{rule.word}
                </span>
            {/each}
            {#each card.chips as chip (chip.kind)}
                <span
                    class="chip"
                    class:now={chip.kind === "turn" || chip.kind === "gameWaits"}
                    class:official={!chip.accent}
                >
                    {@render chipIcons[chip.kind]()}{chip.text}
                </span>
            {/each}
        </div>
    {/if}
{/snippet}

{#if shown}
    <div class="lobby-lists" class:stale={!connected} data-columns={columns}>
        {#if mine.length > 0}
            <section class="lobby-section" aria-labelledby="my-tables-heading">
                <h2 id="my-tables-heading">{words["lobby.myTables"]}</h2>
                <ul class="lobby-list">
                    {#each mine as card (card.id)}
                        <li>
                            <a
                                class="lobby-card"
                                href={resolve("/(start)/t/[id]", { id: card.id })}
                                aria-label={card.openLabel}
                            >
                                {@render cardOfTable(card)}
                            </a>
                        </li>
                    {/each}
                </ul>
            </section>
        {/if}
        {#if open !== null}
            <section class="lobby-section" aria-labelledby="open-tables-heading">
                <h2 id="open-tables-heading">{words["lobby.openTables"]}</h2>
                {#if open.length > 0}
                    <ul class="lobby-list">
                        {#each open as card (card.id)}
                            <li><article class="lobby-card">{@render cardOfTable(card)}</article></li>
                        {/each}
                    </ul>
                {:else}
                    <p class="lobby-quiet" role="status">{words["lobby.noOpenTables"]}</p>
                {/if}
            </section>
        {/if}
        {#if sitFailed}
            <p class="lobby-quiet" role="alert">{words["lobby.sitFailed"]}</p>
        {/if}
    </div>
    {#if !connected}
        <div class="reconnect" role="status"><span class="spin"></span>{words["app.reconnecting"]}</div>
    {/if}
{/if}
