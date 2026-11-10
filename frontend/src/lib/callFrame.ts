import { isCallMode } from "#lib/callSignIn.ts";

// A call-mode address inside a frame is the table of a video call; the call shares it and the frame stays on it.
export function isFramedInCallMode(): boolean {
    return isCallMode(new URL(location.href).search) && window.self !== window.top;
}
