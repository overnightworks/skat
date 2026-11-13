<script lang="ts">
    import { resolve } from "$app/paths";
    import { AiMark } from "overnightworks-design";
    import { onMount, type Snippet } from "svelte";
    import AgentSparkle from "#lib/ui/AgentSparkle.svelte";
    import { words } from "#lib/words.ts";
    import { cardOf, watchLobby, type Card, type ChipKind, type LobbyTable } from "./lobby.ts";

    const COUNTDOWN_MILLISECONDS = 1_000;
    const chipIcons: Record<ChipKind, Snippet> = {
        turn: turnIcon,
        ends: endsIcon,
        seriesOver: trophyIcon,
        result: trophyIcon,
    };

    // How many tables the list shows, for the page that makes room for it.
    let { listed = $bindable(0) }: { listed: number } = $props();

    let tables: LobbyTable[] = $state([]);
    let connected = $state(true);
    let receivedAt = $state(0);
    let now = $state(Date.now());
    let stopwatch = $state(0);

    const cards: Card[] = $derived(tables.map((table) => cardOf(table, now, stopwatch - receivedAt)));
    const columns = $derived(Math.min(cards.length, 3));

    $effect(() => {
        listed = cards.length;
    });

    // A hold is counted down by the page's own stopwatch, which no clock change moves; a new list replaces the count.
    onMount(() => {
        const stop = watchLobby(
            (list) => {
                receivedAt = performance.now();
                stopwatch = receivedAt;
                now = Date.now();
                tables = list;
            },
            (line) => {
                connected = line;
            },
        );
        const tick = setInterval(() => {
            stopwatch = performance.now();
            now = Date.now();
        }, COUNTDOWN_MILLISECONDS);
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

{#if cards.length > 0}
    <section class="my-tables" class:stale={!connected} aria-labelledby="my-tables-heading">
        <h2 id="my-tables-heading">{words["lobby.myTables"]}</h2>
        <ul class="my-tables-list" data-columns={columns}>
            {#each cards as card (card.id)}
                <li>
                    <a
                        class="lobby-card"
                        href={resolve("/(start)/t/[id]", { id: card.id })}
                        aria-label={card.openLabel}
                    >
                        <header>
                            <h3>{card.title}</h3>
                            {#if card.progress !== null}
                                <span class="chip official">{card.progress}</span>
                            {/if}
                        </header>
                        <div class="lobby-row">
                            <div class="lobby-table"><div class="lobby-felt"></div></div>
                            {#each card.seats as seat (seat.seat)}
                                <div class="lobby-seat" class:turn={seat.turn} class:away={seat.away}>
                                    <div class="lobby-chair">
                                        <span class="tile" class:agent={seat.agent} class:free={seat.free}>
                                            {#if seat.agent}
                                                <span class="orb" aria-hidden="true"><AgentSparkle /></span>
                                            {:else}
                                                <span class="initial" aria-hidden="true">{seat.initial}</span>
                                            {/if}
                                        </span>
                                    </div>
                                    {#if seat.turn}
                                        <span class="lobby-mark turn" aria-hidden="true">
                                            <svg viewBox="0 0 24 24" fill="currentColor"
                                                ><path d="M8 5l11 7-11 7z" /></svg
                                            >
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
                                    <span class="lobby-plate">
                                        <b
                                            >{seat.name}{#if seat.agent}<AiMark />{/if}</b
                                        >
                                        {#if seat.hold !== null}
                                            <small title={seat.hold.title}>{seat.hold.note}</small>
                                        {/if}
                                    </span>
                                    {#if seat.total !== null}
                                        <span class="lobby-coaster">{seat.total}</span>
                                    {/if}
                                </div>
                            {/each}
                        </div>
                        {#if card.chips.length > 0}
                            <div class="lobby-chips">
                                {#each card.chips as chip (chip.kind)}
                                    <span class="chip" class:now={chip.kind === "turn"} class:official={!chip.accent}>
                                        {@render chipIcons[chip.kind]()}{chip.text}
                                    </span>
                                {/each}
                            </div>
                        {/if}
                    </a>
                </li>
            {/each}
        </ul>
    </section>
    {#if !connected}
        <div class="reconnect" role="status"><span class="spin"></span>{words["app.reconnecting"]}</div>
    {/if}
{/if}
