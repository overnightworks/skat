<script lang="ts">
    import { onDestroy, type Snippet } from "svelte";
    import {
        bidBar,
        chipTap,
        limitAt,
        livePick,
        passAheadTap,
        passedLimit,
        stepWith,
        takenBack,
        type BidBar,
        type BidLimit,
        type ScaleValue,
    } from "#lib/bidBar.ts";
    import LockIcon from "#lib/ui/LockIcon.svelte";
    import { words } from "#lib/words.ts";
    import {
        setAuctionPlan,
        takeAuctionStep,
        type AuctionAction,
        type Game,
        type PlanChoice,
        type PlanKind,
        type PlanMode,
        type Table,
    } from "../../routes/(start)/tables.ts";

    // Blue is what he says now and brass what the table does for him: a step goes to the auction, a plan to the table.
    let { id, table, note = $bindable() }: { id: string; table: Table; note: string } = $props();

    const CHECK = "M5 12.5l4.5 4.5L19 7.5";
    const UP = "M12 19V5M6 11l6-6 6 6";
    const CROSS = "M6 6l12 12M18 6L6 18";
    const QUESTION = "M9.2 9.2a2.9 2.9 0 1 1 4 2.7c-.7.3-1.2.9-1.2 1.6v.8M12 18h.01";
    const DOTS = "M5.5 12h.01M12 12h.01M18.5 12h.01";
    // A value above his cards is picked by a hold of this length, so a slip of the finger sets nothing high.
    const HOLD_MILLISECONDS = 600;
    const TAKEN_BACK_MILLISECONDS = 2000;
    const TAKEN_BACK: Record<PlanKind, string> = { limit: words["bid.limitCleared"], pass: words["bid.takenBack"] };

    let open = $state(false);
    let picked = $state<number | null>(null);
    let held = $state<number | null>(null);
    let holdTimer: ReturnType<typeof setTimeout> | undefined;
    let back = $state<PlanKind | null>(null);

    // A step is under way from the tap until the stream brings a new version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);

    const bar = $derived(bidBar(table));
    const passed = $derived(passedLimit(table));
    const disabled = $derived(sentAtVersion === table.version);

    // The open scale, a pick and the word of a plan taken back belong to his part in one auction and do not outlive it.
    $effect(() => {
        if (bar !== null) return;
        open = false;
        picked = null;
        back = null;
        release();
    });

    // A plan taken back says so in its line for a moment.
    $effect(() => {
        if (back === null) return;
        const timer = setTimeout(() => {
            back = null;
        }, TAKEN_BACK_MILLISECONDS);
        return () => {
            clearTimeout(timer);
        };
    });

    async function say(action: AuctionAction, value?: number): Promise<void> {
        picked = null;
        note = "";
        sentAtVersion = table.version;
        const answer = await takeAuctionStep(id, crypto.randomUUID(), table.version, action, value);
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["table.commandFailed"];
        }
    }

    // A plan set off his turn moves no version. One set on his turn may have stepped for him: then the keys stay off
    // until the stream brings that version, as after a step of his own.
    async function plan(choice: PlanChoice): Promise<void> {
        const from = table.version;
        const taken = takenBack(table, choice);
        picked = null;
        note = "";
        back = null;
        const answer = await setAuctionPlan(id, crypto.randomUUID(), choice);
        if (answer.kind !== "table") {
            note = words["table.commandFailed"];
            return;
        }
        back = taken;
        if (answer.table.version > from) sentAtVersion = from;
    }

    function tapPass(shown: BidBar): void {
        void (shown.onTurn ? say("pass") : plan(passAheadTap(shown)));
    }

    function release(): void {
        clearTimeout(holdTimer);
        held = null;
    }

    function press({ value, overHand }: ScaleValue): void {
        release();
        if (!overHand) return;
        held = value;
        holdTimer = setTimeout(() => {
            picked = value;
            held = null;
        }, HOLD_MILLISECONDS);
    }

    // The ring fills in the time the hold takes.
    function fillsWhileHeld(ring: HTMLElement): void {
        ring.style.setProperty("--hold-time", `${String(HOLD_MILLISECONDS)}ms`);
    }

    // A pointer's click counts its presses and the keyboard's counts none: the keyboard cannot slip, so it picks at once.
    function tap({ value, overHand }: ScaleValue, presses: number): void {
        if (!overHand || presses === 0) picked = value;
    }

    // The keyboard's value moves to the middle, clear of the fades; a pointer's press stays under the finger.
    function centresForTheKeyboard({ currentTarget }: FocusEvent & { currentTarget: HTMLElement }): void {
        if (currentTarget.matches(":focus-visible"))
            currentTarget.scrollIntoView({ block: "nearest", inline: "center" });
    }

    // The scale opens where the auction stands, with the values just bid still in sight.
    function openAtStanding(view: HTMLElement): void {
        const first = view.querySelector(".v:not(.gone)") as HTMLElement;
        view.scrollLeft = first.offsetLeft - 2 * first.offsetWidth;
    }

    onDestroy(release);
</script>

{#snippet icon(path: string, width: number)}
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width={width}
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
    >
        <path d={path} />
    </svg>
{/snippet}

{#snippet word(text: string | number)}{text}{/snippet}

{#snippet suit(game: Game | null)}
    {#if game !== null}
        <span class={["suit", game]} aria-hidden="true">
            <svg viewBox="0 0 100 100"><use href={`#suit-${game}`} /></svg>
        </span>
    {/if}
{/snippet}

{#snippet upTo(limit: BidLimit)}
    <span class="bis">{@render word(words["bid.upTo"])}{@render suit(limit.game)}<b>{limit.value}</b></span>
{/snippet}

{#snippet question()}{@render icon(QUESTION, 2.2)}{/snippet}

{#snippet lock()}<LockIcon />{/snippet}

<!-- Without a bar the table has said „Weg“ for him, and the keys only show what he chose. -->
{#snippet modeKey(limit: BidLimit, mode: PlanMode, label: string, mark: Snippet)}
    <button
        type="button"
        class:on={limit.mode === mode}
        aria-pressed={limit.mode === mode}
        disabled={bar === null}
        onclick={() => {
            void plan({ kind: "limit", value: limit.value, mode });
        }}
    >
        {@render mark()}{@render word(label)}
    </button>
{/snippet}

{#snippet modes(limit: BidLimit)}
    <span class="mode" role="group" aria-label={words["bid.aboveLimit"]}>
        {@render modeKey(limit, "ask", words["bid.ask"], question)}
        {@render modeKey(limit, "fixed", words["bid.fixed"], lock)}
    </span>
{/snippet}

{#if bar !== null}
    {@const pick = livePick(bar, picked)}
    {@const step = stepWith(bar, pick)}
    <div class="bid">
        <div class="bid-keys">
            {#if step !== null}
                <button
                    type="button"
                    class="button button-stage"
                    class:turnkey={!disabled}
                    {disabled}
                    onclick={() => {
                        void say(step.action, step.value);
                    }}
                >
                    {#if !disabled}
                        <span class="sheen" aria-hidden="true"></span>
                    {/if}
                    {#if step.says === undefined}
                        {@render icon(CHECK, 2.8)}{@render word(words["bid.hold"])}
                    {:else}
                        {@render icon(UP, 2.4)}{@render word(step.says)}
                    {/if}
                </button>
            {/if}
            {#if pick !== null}
                <button
                    type="button"
                    class="button button-brass"
                    onclick={() => {
                        void plan(limitAt(bar, pick));
                    }}
                >
                    {@render word(`${words["bid.upTo"]} ${String(pick)}`)}
                </button>
            {/if}
        </div>
        {#if open}
            <div class="scale" role="group" aria-label={words["bid.allValues"]}>
                <div class="view" {@attach openAtStanding}>
                    {#each bar.scale as each (each.value)}
                        <button
                            type="button"
                            class="v"
                            class:gone={each.gone}
                            class:at={each.standing}
                            class:over={each.overHand}
                            class:mine={each.mine}
                            class:pick={each.value === pick}
                            aria-pressed={each.value === pick}
                            disabled={each.gone}
                            onfocus={centresForTheKeyboard}
                            onpointerdown={() => {
                                press(each);
                            }}
                            onpointerup={release}
                            onpointerleave={release}
                            onpointercancel={release}
                            onclick={(event) => {
                                tap(each, event.detail);
                            }}
                        >
                            {@render suit(each.game)}<b>{each.value}</b>
                            {#if each.holdHint}
                                <span class="hint" aria-hidden="true">{@render word(words["bid.pressAndHold"])}</span>
                            {/if}
                            {#if each.value === held}
                                <i class="hold" {@attach fillsWhileHeld}></i>
                            {/if}
                        </button>
                    {/each}
                </div>
            </div>
        {/if}
        <div class="bid-chips">
            <button
                type="button"
                class="button button-glass"
                class:lit={bar.passAhead}
                aria-pressed={bar.passAhead}
                disabled={bar.onTurn && disabled}
                onclick={() => {
                    tapPass(bar);
                }}
            >
                {@render icon(CROSS, 2.8)}{@render word(words["bid.pass"])}
            </button>
            {#each bar.chips as chip (chip.value)}
                <button
                    type="button"
                    class="bid-chip"
                    class:lit={chip.lit}
                    class:gone={chip.gone}
                    class:rest={bar.passAhead}
                    aria-pressed={chip.lit}
                    aria-label={`${words["bid.upTo"]} ${String(chip.value)}`}
                    disabled={chip.gone}
                    onclick={() => {
                        void plan(chipTap(bar, chip.value));
                    }}
                >
                    {@render suit(chip.game)}<b>{chip.value}</b>
                </button>
            {/each}
            <button
                type="button"
                class="bid-chip more"
                class:lit={open}
                aria-expanded={open}
                aria-label={words["bid.allValues"]}
                onclick={() => {
                    open = !open;
                    picked = null;
                }}
            >
                {@render icon(DOTS, 3.4)}
            </button>
        </div>
        <div class="bid-line">
            {#if bar.asked !== null}
                <p class="asks">{@render upTo(bar.asked)}{@render word(words["bid.asked"])}</p>
            {:else if bar.limit !== null}
                {@render upTo(bar.limit)}
                {@render modes(bar.limit)}
                <button
                    type="button"
                    class="clear"
                    aria-label={words["bid.clearLimit"]}
                    onclick={() => {
                        void plan(null);
                    }}
                >
                    {@render icon(CROSS, 2.8)}
                </button>
            {:else if bar.passAhead}
                <span class="said">{@render icon(CROSS, 2.8)}{@render word(words["bid.passAhead"])}</span>
            {:else if back !== null}
                <span class="said" role="status">{@render icon(CHECK, 2.8)}{@render word(TAKEN_BACK[back])}</span>
            {/if}
        </div>
    </div>
{:else if passed !== null}
    <div class="bid">
        <div class="bid-line dim">
            {@render upTo(passed)}
            {@render modes(passed)}
        </div>
    </div>
{/if}
