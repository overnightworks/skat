// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";
import type { PlayingHand } from "#lib/playView.ts";
import OwnHand from "#lib/ui/OwnHand.svelte";
import { cardName, type Card } from "../../routes/(start)/tables.ts";

const PLAYED: Card = { suit: "kreuz", rank: "ace" };
const KEPT: Card = { suit: "herz", rank: "king" };
const FAR_ABOVE = -200;

describe("a card dropped past the threshold", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(async () => {
        if (mounted !== undefined) await unmount(mounted);
        mounted = undefined;
        document.body.replaceChildren();
    });

    function pointer(type: string, clientY: number): Event {
        return Object.assign(new Event(type, { bubbles: true }), {
            button: 0,
            isPrimary: true,
            pointerId: 1,
            pointerType: "touch",
            clientX: 0,
            clientY,
        });
    }

    it("is not marked again when the same card returns to the hand", async () => {
        const props = $state({ cards: [PLAYED, KEPT] });
        const playing: PlayingHand = {
            legal: [PLAYED, KEPT],
            lifted: null,
            disabled: false,
            tap: () => undefined,
            play: () => Promise.resolve(true),
        };
        mounted = mount(OwnHand, {
            target: document.body,
            props: {
                get cards() {
                    return props.cards;
                },
                game: null,
                playing,
            },
        });
        flushSync();

        const playedButton = document.querySelector<HTMLButtonElement>(`button[aria-label="${cardName(PLAYED)}"]`);
        expect(playedButton).not.toBeNull();
        const button = playedButton as HTMLButtonElement;
        button.setPointerCapture = () => undefined;
        button.dispatchEvent(pointer("pointerdown", 0));
        button.dispatchEvent(pointer("pointerup", FAR_ABOVE));
        await Promise.resolve();
        flushSync();
        expect(document.querySelectorAll(".dragging")).toHaveLength(1);

        props.cards = [KEPT];
        flushSync();
        props.cards = [PLAYED, KEPT];
        flushSync();

        expect(document.querySelectorAll(".dragging")).toHaveLength(0);
    });
});
