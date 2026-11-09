<script lang="ts">
    import { GAME_TOKENS, SUIT_TOKENS } from "#lib/wire.ts";
    import { words } from "#lib/words.ts";
    import {
        declarerStage,
        gameWord,
        SKAT_SIZE,
        takeDeclaringStep,
        togglePicked,
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

    let {
        id,
        table,
        picking = $bindable(),
        note = $bindable(),
    }: { id: string; table: Table; picking?: Picking | undefined; note: string } = $props();

    const stage = $derived(declarerStage(table));
    let picked = $state<Card[]>([]);
    let chosenGame = $state<Game | null>(null);
    // Choosing Hand is a page step: nothing is sent, and a reload returns to the choice.
    let handChosen = $state(false);
    const panel = $derived(stage === "choosing" && handChosen ? "hand" : stage);
    // A step is under way from the tap until the stream brings a new version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    // Whatever was picked belongs to its stage and does not outlive it, as a reload does not either.
    $effect(() => {
        if (stage !== "discarding") picked = [];
        if (stage !== "choosing") handChosen = false;
        if (panel !== "hand" && panel !== "picked") chosenGame = null;
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
                {#each GAME_TOKENS as game (game)}
                    <button
                        type="button"
                        class="game"
                        class:suited={isSuit(game)}
                        aria-pressed={chosenGame === game}
                        aria-label={gameWord(game)}
                        disabled={busy}
                        onclick={() => (chosenGame = game)}
                    >
                        {#if isSuit(game)}
                            <span class="pip" aria-hidden="true">
                                <svg viewBox="0 0 100 100" fill={SUIT_FILL[game]}>
                                    <use href={`#suit-${game}`} />
                                </svg>
                            </span>
                        {/if}
                        <span class="name">{gameWord(game)}</span>
                    </button>
                {/each}
            </div>
            <div class="confirm">
                {#if panel === "hand"}
                    <span class="held">
                        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
                        {`${words.hand}`}
                    </span>
                {/if}
                <button
                    type="button"
                    class="step"
                    disabled={busy || chosenGame === null}
                    onclick={() =>
                        send({
                            action: "declare",
                            game: chosenGame as Game,
                            hand: panel === "hand",
                            ouvert: false,
                            announcement: "none",
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
