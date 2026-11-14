<script lang="ts">
    import { deviceReducesMotion } from "#lib/deviceMotion.svelte.ts";
    import { MOTION_SETS } from "#lib/motionSets.ts";
    import { changeSetting, currentSettings, motionInForce } from "#lib/settings.svelte.ts";
    import { SOUND_SETS } from "#lib/soundSets.ts";
    import { LAST_TRICK_MODES } from "#lib/stage.ts";
    import { prepareVoice, previewSound } from "#lib/tableSound.ts";
    import { words } from "#lib/words.ts";
    import AnchoredPanel from "./AnchoredPanel.svelte";
    import SoundPanel, { type SoundRow } from "./SoundPanel.svelte";

    /** `bar` stands in the table's top row and opens its panel downwards; `strip` stands in the bottom strip and opens it upwards. */
    const { place }: { place: "bar" | "strip" } = $props();

    // The widths of the blessed pictures: a phone's panel and a desktop's, from the width the stylesheet shows the word at.
    const PHONE_PANEL_WIDTH = 328;
    const DESKTOP_PANEL_WIDTH = 360;
    const DESKTOP_FROM = 900;

    let button: HTMLButtonElement | undefined = $state();
    let open = $state(false);
    let viewportWidth = $state(0);

    const settings = $derived(currentSettings());
    const muted = $derived(settings.muted);
    const reduced = $derived(deviceReducesMotion());
    // The pick that just sounded is named until the panel closes.
    let previewed = $state(false);
    $effect(() => {
        if (!open) previewed = false;
    });

    const LAST_TRICK_NAMES = { sweep: "sound.lastTrickSweep", stay: "sound.lastTrickStay" } as const;

    const rows: SoundRow[] = $derived([
        {
            kind: "switch",
            label: words["sound.tone"],
            on: !muted,
            change: (on) => {
                changeSetting("muted", !on);
            },
        },
        {
            kind: "volume",
            label: words["sound.volume"],
            value: settings.volume,
            change: (value: number) => {
                changeSetting("volume", value);
            },
        },
        {
            kind: "choice",
            label: words["sound.sets"],
            options: Object.values(SOUND_SETS).map((set) => ({
                id: set.id,
                name: words[set.name],
                pick: () => {
                    changeSetting("soundSet", set.id);
                    previewed = true;
                    void previewSound();
                },
            })),
            picked: settings.soundSet,
            greyed: false,
            played: previewed && !muted ? words["sound.playsOnce"] : undefined,
        },
        {
            kind: "choice",
            label: words["sound.motion"],
            options: Object.values(MOTION_SETS).map((set) => ({
                id: set.id,
                name: words[set.name],
                pick: () => {
                    changeSetting("motionSet", set.id);
                },
            })),
            picked: settings.motionSet,
            greyed: motionInForce() === undefined,
            note: reduced ? words["sound.reducedMotionNote"] : undefined,
        },
        ...(reduced
            ? [
                  {
                      kind: "switch",
                      label: words["sound.replayMotion"],
                      on: settings.replayMotion,
                      change: (on: boolean) => {
                          changeSetting("replayMotion", on);
                      },
                  } as const,
              ]
            : []),
        {
            kind: "switch",
            label: words["sound.voice"],
            on: settings.voice,
            change: (on: boolean) => {
                changeSetting("voice", on);
                void prepareVoice();
            },
        },
        {
            kind: "choice",
            label: words["sound.lastTrick"],
            options: LAST_TRICK_MODES.map((mode) => ({
                id: mode,
                name: words[LAST_TRICK_NAMES[mode]],
                pick: () => {
                    changeSetting("lastTrick", mode);
                },
            })),
            picked: settings.lastTrick,
            greyed: false,
        },
    ]);
    const name = $derived(muted ? words["sound.muted"] : words["sound.panelName"]);
    const word = $derived(muted ? words["sound.muted"] : words["sound.on"]);
</script>

<svelte:window bind:innerWidth={viewportWidth} />

<button
    bind:this={button}
    type="button"
    class="sound-button sound-{place}"
    class:muted
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-label={name}
    title={name}
    onclick={() => {
        open = true;
    }}
>
    <span class="sound-face">
        {#if muted}
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <mask id="sound-strike" maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24">
                    <rect width="24" height="24" fill="#fff" />
                    <path d="M3.5 3.5l17 17" stroke="#000" stroke-width="5.6" />
                </mask>
                <path mask="url(#sound-strike)" d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" />
                <path d="M3.5 3.5l17 17" />
            </svg>
        {:else}
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" />
                <path d="M15.5 9.2a4 4 0 0 1 0 5.6" />
                <path d="M18.3 6.6a7.8 7.8 0 0 1 0 10.8" />
            </svg>
        {/if}
        <span class="sound-word">{word}</span>
    </span>
</button>
<AnchoredPanel
    anchor={button}
    bind:open
    side={place === "strip" ? "above" : "below"}
    width={viewportWidth >= DESKTOP_FROM ? DESKTOP_PANEL_WIDTH : PHONE_PANEL_WIDTH}
    title={words["sound.panelName"]}
>
    <SoundPanel title={words["sound.panelName"]} {rows} />
</AnchoredPanel>
