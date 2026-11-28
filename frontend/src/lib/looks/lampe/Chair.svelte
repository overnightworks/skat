<script lang="ts">
    import { positionWord, type ChairScene } from "#lib/table/scene.ts";
    import { words } from "#lib/words.ts";

    // One chair with who sits on it. The group's name tells every fact; what stands inside draws the same facts for the
    // eye, so beside the name on the plate it is hidden from a screen reader.
    const { chair }: { chair: ChairScene } = $props();

    const sitter = $derived(chair.sitter);
    const position = $derived(chair.hand === null ? null : positionWord(chair.hand.position));
    // The others' cards lie face down beside their chairs; the viewer's own hand is not the chair's to draw.
    const backs = $derived(
        chair.hand === null || chair.mine ? [] : Array.from({ length: chair.hand.cardsLeft }, (_, index) => index),
    );
</script>

<div
    class="chair"
    role="group"
    aria-label={chair.name}
    data-place={chair.place}
    data-seat={chair.seat}
    data-turn={chair.onTurn}
    data-away={sitter.kind !== "free" && sitter.away}
>
    <span class="portrait" aria-hidden="true">
        {#if sitter.kind === "free"}
            <span class="free"></span>
        {:else if sitter.kind === "agent"}
            <svg class="agent" viewBox="0 0 100 100" focusable="false">
                <path class="agent-body" d="M50 6L88 28V72L50 94L12 72V28Z" />
                <rect class="agent-visor" x="24" y="38" width="52" height="24" rx="12" />
                <rect class="agent-eye" x="35" y="45" width="9" height="10" rx="4.5" />
                <rect class="agent-eye" x="56" y="45" width="9" height="10" rx="4.5" />
            </svg>
        {:else}
            <span class="avatar">{sitter.name.slice(0, 1)}</span>
        {/if}
    </span>
    <span class="plate">
        <span class="who">
            <b class="name">
                {#if sitter.kind === "free"}
                    {words["table.seatFree"]}
                {:else if chair.mine}
                    {words["table.sideYou"]}
                {:else}
                    {sitter.name}
                {/if}
            </b>
            {#if sitter.kind === "agent"}
                <span class="tag ki" aria-hidden="true">{words["table.chairAgent"]}</span>
            {/if}
            {#if position !== null}
                <span class="tag pos" aria-hidden="true">
                    {position.slice(0, 1)}<span class="pos-rest">{position.slice(1)}</span>
                </span>
            {/if}
        </span>
        {#if sitter.kind !== "free" && (sitter.away || chair.hand?.dealer === true || chair.onTurn)}
            <span class="tags" aria-hidden="true">
                {#if chair.hand?.dealer === true}
                    <span class="tag dealer">{words["table.dealer"]}</span>
                {/if}
                {#if sitter.away}
                    <span class="tag away">{words["table.seatAway"]}</span>
                {/if}
                {#if chair.onTurn}
                    <span class="tag turn">{words["table.chairOnTurn"]}</span>
                {/if}
            </span>
        {/if}
    </span>
    {#if backs.length > 0}
        <span class="backs" aria-hidden="true">
            {#each backs as back (back)}
                <i></i>
            {/each}
            <b>{backs.length}</b>
        </span>
    {/if}
</div>
