<script lang="ts">
    import { mayDeclareGrandHand, pushStage } from "#lib/pushView.ts";
    import { words } from "#lib/words.ts";
    import {
        SKAT_SIZE,
        takePushingStep,
        togglePicked,
        type Card,
        type Picking,
        type PushingStep,
        type Table,
    } from "../../routes/(start)/tables.ts";

    let {
        id,
        table,
        picking = $bindable(),
        note = $bindable(),
    }: { id: string; table: Table; picking?: Picking | undefined; note: string } = $props();

    // The first tap on the Grand Hand key arms it for this long; only the second tap inside the time declares.
    const ARMED_MILLISECONDS = 3000;

    const stage = $derived(pushStage(table));
    const grandHandKey = $derived(mayDeclareGrandHand(table));
    let armed = $state(false);
    let grandHandButton = $state<HTMLButtonElement | undefined>();
    let picked = $state<Card[]>([]);
    // A step is under way from the tap until the stream brings a new version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    // Whatever was picked belongs to its stage and does not outlive it, as a reload does not either.
    $effect(() => {
        if (stage !== "discarding") picked = [];
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
                      allowed: table.hand?.pushing?.put_back_cards ?? [],
                  }
                : undefined;
    });

    // Whatever is tapped but the armed key, and the time, disarm it.
    $effect(() => {
        if (!armed) return;
        const timer = setTimeout(() => {
            armed = false;
        }, ARMED_MILLISECONDS);
        const disarmOnOtherTap = (event: PointerEvent): void => {
            if (!(event.target instanceof Node && grandHandButton?.contains(event.target))) armed = false;
        };
        window.addEventListener("pointerdown", disarmOnOtherTap);
        return () => {
            clearTimeout(timer);
            window.removeEventListener("pointerdown", disarmOnOtherTap);
        };
    });

    $effect(() => {
        if (!grandHandKey || busy) armed = false;
    });

    function tapGrandHand(): void {
        if (!armed) {
            armed = true;
            return;
        }
        armed = false;
        void send({ action: "grand_hand" });
    }

    async function send(step: PushingStep): Promise<void> {
        note = "";
        sentAtVersion = table.version;
        const answer = await takePushingStep(id, table.version, crypto.randomUUID(), step);
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["declare.commandFailed"];
        }
    }
</script>

{#if stage !== null}
    <div class={`declare pushing ${stage}`} class:grand={grandHandKey}>
        {#if stage === "choosing"}
            <div class="line">
                <button type="button" class="step" disabled={busy} onclick={() => send({ action: "take" })}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                    {`${words["push.takeSkat"]}`}
                </button>
                <button type="button" class="step glass" disabled={busy} onclick={() => send({ action: "push" })}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h14M13 6l6 6-6 6" /></svg>
                    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                    {`${words["table.push"]}`}
                </button>
            </div>
            {#if grandHandKey}
                <div class="line">
                    <button
                        type="button"
                        class={["step", "grand", armed ? "armed" : "glass"]}
                        disabled={busy}
                        bind:this={grandHandButton}
                        onclick={tapGrandHand}
                    >
                        <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                        {`${armed ? words["push.grandHandAsk"] : words["push.grandHand"]}`}
                        {#if armed}<i aria-hidden="true"></i>{/if}
                    </button>
                </div>
            {/if}
        {:else}
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
                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
                {`${words["declare.putBack"]}`}
            </button>
        {/if}
    </div>
{/if}
