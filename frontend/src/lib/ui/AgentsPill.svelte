<script lang="ts">
    import { untrack } from "svelte";
    import { AgentControl, AiMark, type AgentControlRefusal, type KitWords } from "overnightworks-design";
    import { words } from "#lib/words.ts";
    import { followAgents, type AgentsControl, type AgentsFollower } from "../../routes/(start)/tables.ts";

    // The popover keeps this far from either edge of the viewport; it is as wide as the kit's list is drawn for.
    const EDGE_MARGIN = 16;
    const PHONE_POPOVER_WIDTH = 300;
    const DESKTOP_POPOVER_WIDTH = 320;
    const DESKTOP_MIN_WIDTH = 900;

    // `streamedVersion` is the version of the latest table the page's stream brought, null before the first: the first
    // one means the viewer has a stream on the table, which the control needs, and each later one is read only while
    // the list is open.
    const {
        tableId,
        streamedVersion,
        kitWords,
    }: { tableId: string; streamedVersion: number | null; kitWords: KitWords } = $props();

    let control = $state<AgentsControl>({ shown: false, rows: [] });
    let refusal = $state<AgentControlRefusal | undefined>();
    let open = $state(false);
    let anchor = $state<HTMLElement | undefined>();
    let popover = $state<HTMLElement | undefined>();
    let placement = $state({ width: 0, left: 0, caret: 0 });
    let follower: AgentsFollower | undefined;
    let sawFirstTable = false;

    $effect(() => {
        const following = followAgents(
            tableId,
            (answer) => (control = answer),
            (reason) => (refusal = reason ?? undefined),
        );
        follower = following;
        return () => {
            following.stop();
        };
    });

    $effect(() => {
        if (streamedVersion === null) return;
        const firstTable = !sawFirstTable;
        sawFirstTable = true;
        if (firstTable || untrack(() => open)) void follower?.read();
    });

    // Anchored over the pill's middle, and inside the margin of both edges.
    function place(): void {
        if (anchor === undefined) return;
        const pill = anchor.getBoundingClientRect();
        const wanted = innerWidth >= DESKTOP_MIN_WIDTH ? DESKTOP_POPOVER_WIDTH : PHONE_POPOVER_WIDTH;
        const width = Math.min(wanted, innerWidth - 2 * EDGE_MARGIN);
        const middle = pill.left + pill.width / 2;
        const left = Math.max(EDGE_MARGIN, Math.min(middle - width / 2, innerWidth - EDGE_MARGIN - width));
        const next = { width, left: left - pill.left, caret: middle - left };
        if (next.width !== placement.width || next.left !== placement.left || next.caret !== placement.caret) {
            placement = next;
        }
    }

    // The pill moves when the table around it changes (a hand deals, a plaque stands) while the list stays open, so an
    // open list follows its pill frame by frame.
    $effect(() => {
        if (!open) return;
        let frame = requestAnimationFrame(function follow() {
            place();
            frame = requestAnimationFrame(follow);
        });
        return () => {
            cancelAnimationFrame(frame);
        };
    });

    // The popover's place is set on the element, so the stylesheet owns every other property of it.
    $effect(() => {
        popover?.style.setProperty("width", `${String(placement.width)}px`);
        popover?.style.setProperty("left", `${String(placement.left)}px`);
        popover?.style.setProperty("--caret", `${String(placement.caret)}px`);
    });

    function toggle(): void {
        open = !open;
        refusal = undefined;
        if (open) {
            place();
            void follower?.read();
        }
    }

    function closeOutside(event: PointerEvent): void {
        if (open && event.target instanceof Node && anchor?.contains(event.target) !== true) {
            open = false;
            refusal = undefined;
        }
    }
</script>

<svelte:window onpointerdown={closeOutside} onresize={place} />

{#if control.shown}
    <span class="pill-anchor" bind:this={anchor}>
        <button
            type="button"
            class="copy agents"
            class:on={open}
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-label={words["agents.pill"]}
            onclick={toggle}
        >
            <AiMark /><span class="word">{words["agents.pill"]}</span>
        </button>
        {#if open}
            <div class="agents-pop" role="dialog" aria-label={words["agents.pill"]} bind:this={popover}>
                <AgentControl
                    rows={control.rows}
                    onCall={(key) => void follower?.call(key)}
                    {refusal}
                    words={kitWords}
                />
            </div>
        {/if}
    </span>
{/if}
