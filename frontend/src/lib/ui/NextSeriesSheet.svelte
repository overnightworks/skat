<script lang="ts">
    import { untrack } from "svelte";
    import { closeOnEscape } from "#lib/closeOnEscape.ts";
    import AnswerClock from "#lib/ui/AnswerClock.svelte";
    import { words } from "#lib/words.ts";
    import { requestOf } from "../../routes/(start)/openingRules.ts";
    import SettingsBody from "../../routes/(start)/SettingsBody.svelte";
    import type { NextSettings, OptionsRequest, Outcome } from "../../routes/(start)/tables.ts";

    // The start sheet's settings body over the series end, filled with what the next series begins with. `takenBack`
    // names the seats whose „Neue Serie“ a save takes back, `answerBy` is the instant a silent seat ends the table (null
    // while no minute runs), `settingsChanged` says that the settings shown are those another seat saved meanwhile; `save` sends
    // the settings and answers the server's outcome.
    const {
        initial,
        settingsChanged,
        answerBy,
        takenBack,
        save,
        oncancel,
    }: {
        initial: NextSettings;
        settingsChanged: boolean;
        answerBy: string | null;
        takenBack: string | null;
        save: (commandId: string, length: number, options: OptionsRequest | undefined) => Promise<Outcome>;
        oncancel: () => void;
    } = $props();

    let length = $state(untrack(() => initial.game_count));
    let sheet = $state(untrack(() => initial.options));
    let saving = $state(false);
    let failed = $state(false);
    let commandId = crypto.randomUUID();

    // Other settings are another command, so a retry never sends two requests under one id.
    function changed(): void {
        commandId = crypto.randomUUID();
    }

    async function submit(): Promise<void> {
        saving = true;
        const outcome = await save(commandId, length, requestOf(sheet));
        saving = false;
        failed = outcome.kind !== "table";
    }
</script>

<div class="scrim"></div>
<div
    class="sheet next-series"
    role="dialog"
    aria-modal="true"
    aria-label={words["table.nextSeries"]}
    {@attach closeOnEscape(() => {
        if (!saving) oncancel();
    })}
>
    <h3>{words["table.nextSeries"]}</h3>
    {#if answerBy !== null}
        <AnswerClock until={answerBy} ends />
    {/if}
    {#if settingsChanged}
        <p role="status">{words["table.nextSeriesChanged"]}</p>
    {/if}
    <SettingsBody bind:length bind:sheet disabled={saving} onchange={changed} />
    {#if takenBack !== null}
        <p class="takeback">{takenBack}</p>
    {/if}
    {#if failed}
        <p role="alert">{words["table.commandFailed"]}</p>
    {/if}
    <div class="btns">
        <button type="button" class="confirm" disabled={saving} onclick={submit}>
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.8"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <path d="M5 12.5l4.5 4.5L19 7.5" />
            </svg>
            <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
            {`${words["table.nextSeriesSave"]}`}
        </button>
        <button type="button" class="cancel" disabled={saving} onclick={oncancel}>
            {words["table.nextSeriesCancel"]}
        </button>
    </div>
</div>
