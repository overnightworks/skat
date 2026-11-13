// @vitest-environment jsdom
import { flushSync, mount, unmount } from "svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import SitQuestion from "#lib/ui/SitQuestion.svelte";

describe("the question before a sit", () => {
    let mounted: ReturnType<typeof mount> | undefined;

    afterEach(() => {
        if (mounted !== undefined) void unmount(mounted);
        mounted = undefined;
        document.body.innerHTML = "";
    });

    function ask(oncancel: () => void): void {
        mounted = mount(SitQuestion, {
            target: document.body,
            props: { formerHolder: null, onsit: vi.fn(), oncancel },
        });
        flushSync();
    }

    it("closes on Escape", () => {
        const oncancel = vi.fn();
        ask(oncancel);

        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

        expect(oncancel).toHaveBeenCalledOnce();
    });

    it("stays open on any other key", () => {
        const oncancel = vi.fn();
        ask(oncancel);

        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));

        expect(oncancel).not.toHaveBeenCalled();
    });

    it("stops listening once it is gone", () => {
        const oncancel = vi.fn();
        ask(oncancel);
        void unmount(mounted as ReturnType<typeof mount>);
        mounted = undefined;

        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

        expect(oncancel).not.toHaveBeenCalled();
    });
});
