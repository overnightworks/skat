<script lang="ts">
    import type { Snippet } from "svelte";
    import { applyPanelPlace, placePanel, type PanelSide } from "#lib/panelPlace.ts";

    let {
        anchor,
        open = $bindable(),
        side,
        width,
        title,
        children,
    }: {
        /** The button the panel hangs on; Escape and every closing hand the focus back to it. */
        anchor: HTMLElement | undefined;
        open: boolean;
        side: PanelSide;
        /** The width it wants; a narrower viewport shrinks it. */
        width: number;
        title: string;
        children: Snippet;
    } = $props();

    let overlay: HTMLDivElement | undefined = $state();
    let panel: HTMLDivElement | undefined = $state();

    function place(): void {
        if (anchor === undefined || overlay === undefined || panel === undefined) return;
        const view = { width: overlay.clientWidth, height: overlay.clientHeight };
        applyPanelPlace(panel, placePanel(anchor.getBoundingClientRect(), view, width, side));
    }

    // The popover is shown from script, so any button can drive it; its toggle event is what `open` follows.
    $effect(() => {
        if (overlay === undefined) return;
        const shown = overlay.matches(":popover-open");
        if (open && !shown) {
            overlay.showPopover();
            place();
            panel?.querySelector<HTMLElement>("input, button, a[href]")?.focus();
        } else if (!open && shown) {
            overlay.hidePopover();
        } else if (open) {
            place();
        }
    });

    function followToggle(event: Event): void {
        open = (event as ToggleEvent).newState === "open";
        if (!open) anchor?.focus();
    }

    // The overlay covers the viewport, so the tap that closes the panel lands on the overlay and reaches nothing under it.
    function closeAtTap(event: MouseEvent): void {
        if (event.target === overlay) open = false;
    }
</script>

<svelte:window
    onresize={() => {
        if (open) place();
    }}
/>

<!-- Escape closes the popover natively; the click is the tap on everything around the panel. -->
<div
    class="anchored-overlay"
    popover="auto"
    role="presentation"
    bind:this={overlay}
    ontoggle={followToggle}
    onclick={closeAtTap}
>
    <div class="anchored-panel" class:above={side === "above"} role="dialog" aria-label={title} bind:this={panel}>
        {@render children()}
    </div>
</div>
