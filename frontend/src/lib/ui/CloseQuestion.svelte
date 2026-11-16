<script lang="ts">
    import { words } from "#lib/words.ts";
    import PowerMark from "./PowerMark.svelte";
    import { closeTable } from "../../routes/(start)/tables.ts";

    // The question the opener's "Tisch schließen" row asks: "Schließen" sends the close, "Abbrechen" asks no more and
    // sends nothing; both hand the page back through `onanswered`.
    let { id, note = $bindable(), onanswered }: { id: string; note: string; onanswered: () => void } = $props();

    async function confirm(): Promise<void> {
        onanswered();
        note = "";
        if ((await closeTable(id, crypto.randomUUID())).kind !== "table") note = words["table.commandFailed"];
    }
</script>

<div class="scrim"></div>
<div class="sheet question" role="dialog" aria-modal="true" aria-label={words["table.closeQuestion"]}>
    <span class="glyph"><PowerMark /></span>
    <h3>{words["table.closeQuestion"]}</h3>
    <div class="btns">
        <button type="button" class="confirm leave" onclick={confirm}>
            <PowerMark />
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
            {`${words["table.closeConfirm"]}`}
        </button>
        <button type="button" class="cancel" onclick={onanswered}>
            {words["table.closeCancel"]}
        </button>
    </div>
</div>
