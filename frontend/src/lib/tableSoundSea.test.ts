import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakePort, soundAt } from "./tableSound.fixtures.ts";
import { stubBrowser } from "../testing/stubBrowser.ts";

describe("the sea under the table", () => {
    it("runs while the table wants it and goes quiet when it no longer does", () => {
        const port = new FakePort();
        const sound = soundAt(port);

        sound.ambience("sea");
        const running = port.sea.at(-1) as number;
        sound.ambience(undefined);

        expect([running > 0, port.sea.at(-1)]).toEqual([true, 0]);
    });
});

describe("the page's sea", () => {
    beforeEach(() => {
        vi.resetModules();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("starts the sea of the page once the first tap woke the sound and the table wants it", async () => {
        const { started, listeners } = stubBrowser({ reducedMotion: true });
        const { armSound, runAmbience } = await import("./tableSound.ts");
        armSound();
        listeners.get("pointerup")?.();
        const woken = started.length;

        runAmbience("sea");

        expect(started.length).toBeGreaterThan(woken);
    });

    it("starts the pub's murmur once the first tap woke the sound and the table wants it", async () => {
        const { started, listeners } = stubBrowser({ reducedMotion: true });
        const { armSound, runAmbience } = await import("./tableSound.ts");
        armSound();
        listeners.get("pointerup")?.();
        const woken = started.length;

        runAmbience("pub");

        expect(started.length).toBeGreaterThan(woken);
    });

    it("starts no sea on a muted device", async () => {
        const { started, listeners } = stubBrowser({ reducedMotion: true, stored: JSON.stringify({ muted: true }) });
        const { armSound, runAmbience } = await import("./tableSound.ts");
        armSound();
        listeners.get("pointerup")?.();
        const woken = started.length;

        runAmbience("sea");

        expect(started).toHaveLength(woken);
    });
});
