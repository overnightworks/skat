import type { Attachment } from "svelte/attachments";

// A sheet that blocks the page closes on Escape as the anchored panel does; it listens while it is on the page.
export function closeOnEscape(close: () => void): Attachment {
    return () => {
        const listener = (event: KeyboardEvent): void => {
            if (event.key === "Escape") close();
        };
        window.addEventListener("keydown", listener);
        return () => {
            window.removeEventListener("keydown", listener);
        };
    };
}
