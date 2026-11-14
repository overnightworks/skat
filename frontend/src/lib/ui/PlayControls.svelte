<script lang="ts">
    import { cardsToPlay, type PlayingHand } from "#lib/playView.ts";
    import { words } from "#lib/words.ts";
    import { includesCard, playCard, type Card, type Table } from "../../routes/(start)/tables.ts";

    let {
        id,
        table,
        playing = $bindable(),
        note = $bindable(),
    }: { id: string; table: Table; playing?: PlayingHand | undefined; note: string } = $props();

    const legal = $derived(cardsToPlay(table));
    let lifted = $state<Card | null>(null);
    // A card is under way from the tap until the stream brings a new version; only a refusal ends it sooner.
    let sentAtVersion = $state<number | null>(null);
    const busy = $derived(sentAtVersion === table.version);

    // A lifted card belongs to the viewer's turn and does not outlive it, as a reload does not either.
    $effect(() => {
        if (legal === null) lifted = null;
    });

    // Only this component knows which card is lifted; the hand on the table draws it through the page.
    $effect(() => {
        playing =
            legal === null
                ? undefined
                : {
                      legal,
                      lifted,
                      disabled: busy,
                      tap: (card) => {
                          if (lifted !== null && includesCard([lifted], card)) void send(card);
                          else lifted = card;
                      },
                      play: send,
                  };
    });

    async function send(card: Card): Promise<boolean> {
        note = "";
        sentAtVersion = table.version;
        const answer = await playCard(id, table.version, crypto.randomUUID(), card);
        if (answer.kind !== "table") {
            sentAtVersion = null;
            note = words["play.commandFailed"];
        }
        return answer.kind === "table";
    }
</script>
