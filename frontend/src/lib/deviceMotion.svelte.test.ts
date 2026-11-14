import { afterEach, describe, expect, it, vi } from "vitest";

async function freshDevice() {
    vi.resetModules();
    return import("./deviceMotion.svelte.ts");
}

function stubDevice(reduces: boolean) {
    let announce: ((event: { matches: boolean }) => void) | undefined;
    vi.stubGlobal("window", {
        matchMedia: () => ({
            matches: reduces,
            addEventListener: (_type: string, handler: (event: { matches: boolean }) => void) => {
                announce = handler;
            },
        }),
    });
    return { announce: (matches: boolean) => announce?.({ matches }) };
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("the device's motion", () => {
    it("is reduced until the device has been asked", async () => {
        const { deviceReducesMotion } = await freshDevice();

        expect(deviceReducesMotion()).toBe(true);
    });

    it.each([true, false])("reads %s from the device", async (reduces) => {
        stubDevice(reduces);
        const { deviceReducesMotion, watchDeviceMotion } = await freshDevice();

        watchDeviceMotion();

        expect(deviceReducesMotion()).toBe(reduces);
    });

    it("follows the device when the player changes its setting", async () => {
        const device = stubDevice(true);
        const { deviceReducesMotion, watchDeviceMotion } = await freshDevice();
        watchDeviceMotion();

        device.announce(false);

        expect(deviceReducesMotion()).toBe(false);
    });

    it("asks the device once however often it is watched", async () => {
        const asked = vi.fn(() => ({ matches: true, addEventListener: vi.fn() }));
        vi.stubGlobal("window", { matchMedia: asked });
        const { watchDeviceMotion } = await freshDevice();

        watchDeviceMotion();
        watchDeviceMotion();

        expect(asked).toHaveBeenCalledTimes(1);
    });
});
