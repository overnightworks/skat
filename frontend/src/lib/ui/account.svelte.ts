import { ACCOUNT_PATH } from "#lib/wire.ts";
import { words } from "#lib/words.ts";

const SIGNED_OUT_STATUS = 401;

const account: { name: string | null } = $state({ name: null });

export function menuName(): string {
    return account.name ?? words["account.title"];
}

// A session that ended while the page was open goes through the sign-in again; any other failure
// leaves the menu with its unnamed label, which is visible and harmless.
export async function readAccount(): Promise<void> {
    let answer: Response;
    try {
        answer = await fetch(ACCOUNT_PATH);
    } catch {
        return;
    }
    if (answer.status === SIGNED_OUT_STATUS) {
        location.reload();
        return;
    }
    if (!answer.ok) return;
    const { name } = (await answer.json()) as { name?: unknown };
    if (typeof name === "string") account.name = name;
}
