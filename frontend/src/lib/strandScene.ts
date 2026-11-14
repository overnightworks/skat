/** The beach behind a Strandbar table, as the blessed scenes draw it: dusk sky, the sea's horizon with the sun's path, foam along the shore, sand. */
export interface Dot {
    readonly x: number;
    readonly y: number;
    readonly r: number;
    readonly opacity: number;
    readonly light: boolean;
}

export interface Beach {
    readonly width: number;
    readonly height: number;
    readonly horizon: number;
    readonly shore: number;
    readonly sunX: number;
    readonly sunRadius: number;
    readonly glowRadius: number;
    readonly stars: readonly Dot[];
    readonly speckle: readonly Dot[];
    /** The sun's path on the water: bars that narrow towards the shore. */
    readonly sunPath: readonly { x: number; y: number; width: number; height: number; opacity: number }[];
    readonly seaLines: readonly { d: string; opacity: number }[];
    readonly foam: readonly { d: string; width: number; opacity: number; shift: number }[];
    /** The string of lights over the desktop's sky. */
    readonly bulbs: readonly { x: number; y: number }[];
    /** How far the first foam wave reaches over the sand. */
    readonly foamDepth: number;
}

export type BeachSize = "phone" | "desktop";

export const BEACH_VIEWS: Record<BeachSize, { width: number; height: number }> = {
    phone: { width: 390, height: 844 },
    desktop: { width: 1280, height: 800 },
};

const PARK_MILLER = 16807;
const PARK_MODULUS = 2147483647;

// A seeded sequence, so the stars and the sand lie where they lay in the blessed picture on every load.
function seeded(): () => number {
    let seed = 7;
    return () => {
        seed = (seed * PARK_MILLER) % PARK_MODULUS;
        return seed / PARK_MODULUS;
    };
}

function wave(width: number, y: number, amplitude: number, length: number): string {
    let path = `M-${String(length)} ${String(y)}`;
    for (let x = -length; x <= width + length; x += length) {
        path += `Q${String(x + length / 4)} ${String(y - amplitude)} ${String(x + length / 2)} ${String(y)}T${String(x + length)} ${String(y)}`;
    }
    return path;
}

export function beachOf(size: BeachSize): Beach {
    const desktop = size === "desktop";
    const { width, height } = BEACH_VIEWS[size];
    const horizon = Math.round(height * (desktop ? 0.21 : 0.095));
    const shore = Math.round(height * (desktop ? 0.38 : 0.17));
    const sunX = Math.round(width * (desktop ? 0.7 : 0.68));
    const random = seeded();
    const stars = Array.from({ length: desktop ? 26 : 14 }, (): Dot => {
        const x = Math.round(random() * width);
        const y = Math.round(random() * horizon * 0.8);
        return { x, y, r: 0.6 + random() * 0.9, opacity: 0.45 + random() * 0.5, light: true };
    });
    const scale = desktop ? 1.6 : 1;
    const sunPath = Array.from({ length: 9 }, (_, index) => {
        const barWidth = (52 - index * 5.5) * scale;
        return {
            x: sunX - barWidth / 2,
            y: horizon + 4 + index * (desktop ? 8 : 6),
            width: barWidth,
            height: desktop ? 3 : 2.4,
            opacity: 0.7 - index * 0.07,
        };
    });
    const seaCount = desktop ? 9 : 4;
    const seaLines = Array.from({ length: seaCount }, (_, index) => ({
        d: wave(
            width,
            horizon + 14 + index * ((shore - horizon - 20) / seaCount),
            desktop ? 2.5 : 2,
            desktop ? 70 : 50,
        ),
        opacity: 0.05 + index * 0.014,
    }));
    const length = desktop ? 90 : 60;
    const foam = [
        { d: wave(width, shore, desktop ? 4 : 3, length), width: 0, opacity: 0.5, shift: 0 },
        {
            d: wave(width, shore + (desktop ? 5 : 3), desktop ? 4 : 3, length),
            width: desktop ? 3 : 2.4,
            opacity: 0.8,
            shift: 1,
        },
        { d: wave(width, shore + (desktop ? 18 : 11), desktop ? 3 : 2.4, length), width: 1.6, opacity: 0.3, shift: 2 },
    ];
    const speckle = Array.from({ length: desktop ? 150 : 90 }, (): Dot => {
        const x = Math.round(random() * width);
        const y = Math.round(shore + 16 + random() * (height - shore - 16));
        return { x, y, r: 0.7 + random() * 1.3, opacity: 0.22, light: random() > 0.5 };
    });
    const bulbs = desktop
        ? Array.from({ length: 17 }, (_, index) => ({
              x: Math.round(330 + index * 38.75),
              y: Math.round(22 + Math.sin((index / 16) * Math.PI) * 22 + 12),
          }))
        : [];
    return {
        width,
        height,
        horizon,
        shore,
        sunX,
        sunRadius: desktop ? 40 : 26,
        glowRadius: desktop ? 260 : 150,
        stars,
        speckle,
        sunPath,
        seaLines,
        foam,
        bulbs,
        foamDepth: desktop ? 26 : 16,
    };
}
