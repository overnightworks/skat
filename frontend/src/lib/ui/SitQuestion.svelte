<script lang="ts">
    import { sitQuestionLine } from "#lib/openChair.ts";
    import { words } from "#lib/words.ts";

    // `formerHolder` is the name of whoever held the open chair in the running hand, or null when it was not written down.
    const { formerHolder, onsit, oncancel }: { formerHolder: string | null; onsit: () => void; oncancel: () => void } =
        $props();
</script>

<div class="scrim"></div>
<div class="sheet question" role="dialog" aria-modal="true" aria-label={words["table.sitQuestion"]}>
    <span class="glyph">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
        </svg>
    </span>
    <h3>{words["table.sitQuestion"]}</h3>
    <p>{sitQuestionLine(formerHolder)}</p>
    <div class="btns">
        <button type="button" class="confirm" onclick={onsit}>
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
                aria-hidden="true"
            >
                <path d="M12 5v14M5 12h14" />
            </svg>
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
            {`${words["table.sitDown"]}`}
        </button>
        <button type="button" class="cancel" onclick={oncancel}>{words["table.sitQuestionCancel"]}</button>
    </div>
</div>
