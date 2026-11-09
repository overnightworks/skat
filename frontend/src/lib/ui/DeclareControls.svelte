<script lang="ts">
    import { GAME_TOKENS, SUIT_TOKENS } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import {
        declarerStage,
        gameLabel,
        SKAT_SIZE,
        takeDeclaringStep,
        togglePicked,
        type Announcement,
        type Card,
        type DeclaringStep,
        type Game,
        type Picking,
        type Suit,
        type Table,
    } from "../../routes/(start)/tables.ts";

    // The same pips the picture draws on the hand's cards.
    const SUIT_FILL: Record<Suit, string> = { kreuz: "#17191c", pik: "#14873f", herz: "#d81f35", karo: "#ec9800" };
    const SUITS: ReadonlySet<Game> = new Set(SUIT_TOKENS);

    // A tile names a game and whether it is played open; Null ouvert is the one open game that can follow the take.
    type Tile = { game: Game; ouvert: boolean };
    const TILES: readonly Tile[] = GAME_TOKENS.flatMap((game): Tile[] =>
        game === "null"
            ? [
                  { game, ouvert: false },
                  { game, ouvert: true },
              ]
            : [{ game, ouvert: false }],
    );
    // The tiles stand on two rows, as the picture draws them: the four suits, then the rest.
    const TILE_ROWS: readonly (readonly Tile[])[] = [
        TILES.filter((tile) => SUITS.has(tile.game)),
        TILES.filter((tile) => !SUITS.has(tile.game)),
    ];
    // One rung of Hand's ladder is chosen at a time; the engine adds Schwarz to an ouvert game.
    type Rung = Announcement | "ouvert";

    let {
        id,
        table,
        picking = $bindable(),
        note = $bindable(),
    }: { id: string; table: Table; picking?: Picking | undefined; note: string } = $props();

    const stage = $derived(declarerStage(table));
    let picked = $state<Card[]>([]);
    let chosen = $state<Tile | null>(null);
    // Choosing Hand is a page step: nothing is sent, and a reload returns to the choice.
    let handChosen = $state(false);
    // Hand's levels: one at a time, and Null has none.
    let level = $state<Rung>("none");
    const panel = $derived(stage === "choosing" && handChosen ? "hand" : stage);
    // A step is under way from the tap until the stream brings a new version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    // Whatever was picked belongs to its stage and does not outlive it, as a reload does not either.
    $effect(() => {
        if (stage !== "discarding") picked = [];
        if (stage !== "choosing") handChosen = false;
        if (panel !== "hand" && panel !== "picked") chosen = null;
        if (panel !== "hand") level = "none";
    });

    // Only this component knows what is picked; the hand on the table draws it through the page.
    $effect(() => {
        picking =
            stage === "discarding"
                ? {
                      picked,
                      disabled: busy,
                      toggle: (card) => {
                          picked = togglePicked(picked, card);
                      },
                  }
                : undefined;
    });

    async function send(step: DeclaringStep): Promise<void> {
        note = "";
        sentAtVersion = table.version;
        const answer = await takeDeclaringStep(id, table.version, crypto.randomUUID(), step);
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words.commandFailed;
        }
    }

    const LEVELS: readonly { token: Exclude<Rung, "none">; word: string }[] = [
        { token: "schneider", word: words.levelSchneider },
        { token: "schwarz", word: words.levelSchwarz },
        { token: "ouvert", word: words.levelOuvert },
    ];

    function announcementOf(rung: Rung): Announcement {
        return rung === "ouvert" ? "none" : rung;
    }

    function isSuit(game: Game): game is Suit {
        return SUITS.has(game);
    }
</script>

{#if panel !== null}
    <div class={`declare ${panel}`}>
        {#if panel === "choosing"}
            <button type="button" class="step" disabled={busy} onclick={() => send({ action: "take" })}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                {`${words.takeSkat}`}
            </button>
            <button type="button" class="step hand" disabled={busy} onclick={() => (handChosen = true)}>
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                {`${words.hand}`}
            </button>
        {:else if panel === "discarding"}
            <div class="slots" aria-hidden="true">
                {#each [0, 1] as slot (slot)}
                    <span class="slot">
                        <svg viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
                    </span>
                {/each}
            </div>
            <button
                type="button"
                class="step"
                disabled={busy || picked.length !== SKAT_SIZE}
                onclick={() => send({ action: "put_back", cards: picked })}
            >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                {`${words.putBack}`}
            </button>
        {:else}
            <div class="games">
                {#each TILE_ROWS as row, rowIndex (rowIndex)}
                    <div class="tiles">
                        {#each row as tile (`${tile.game}${String(tile.ouvert)}`)}
                            {@const game = tile.game}
                            {@const label = gameLabel({ ...tile, hand: false })}
                            <button
                                type="button"
                                class="game"
                                class:suited={isSuit(game)}
                                aria-pressed={chosen?.game === game && chosen.ouvert === tile.ouvert}
                                aria-label={label}
                                disabled={busy}
                                onclick={() => {
                                    chosen = tile;
                                    if (game === "null") level = "none";
                                }}
                            >
                                {#if isSuit(game)}
                                    <span class="pip" aria-hidden="true">
                                        <svg viewBox="0 0 100 100" fill={SUIT_FILL[game]}>
                                            <use href={`#suit-${game}`} />
                                        </svg>
                                    </span>
                                {/if}
                                <span class="name">{label}</span>
                            </button>
                        {/each}
                    </div>
                {/each}
            </div>
            <div class="confirm">
                {#if panel === "hand"}
                    <div class="ladder">
                        <span class="held">
                            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                            {`${words.hand}`}
                        </span>
                        {#if chosen?.game !== "null"}
                            {#each LEVELS as { token, word } (token)}
                                <button
                                    type="button"
                                    aria-pressed={level === token}
                                    disabled={busy}
                                    onclick={() => (level = level === token ? "none" : token)}
                                >
                                    {word}
                                </button>
                            {/each}
                        {/if}
                    </div>
                {/if}
                <button
                    type="button"
                    class="step"
                    disabled={busy || chosen === null}
                    onclick={() =>
                        send({
                            action: "declare",
                            game: (chosen as Tile).game,
                            hand: panel === "hand",
                            ouvert: (chosen as Tile).ouvert || level === "ouvert",
                            announcement: announcementOf(level),
                        })}
                >
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                    {`${words.announceGame}`}
                </button>
            </div>
        {/if}
    </div>
{/if}
