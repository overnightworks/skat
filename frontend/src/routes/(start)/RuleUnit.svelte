<script lang="ts">
    import RuleMark from "#lib/ui/RuleMark.svelte";
    import { words } from "#lib/words.ts";
    import {
        isOn,
        QUESTIONS,
        switchRule,
        toggleTrigger,
        TRIGGER_SWITCHES,
        triggerOn,
        type RuleRow,
    } from "./openingRules.ts";
    import type { Options } from "./tables.ts";

    // One rule of the opening sheet: its row with the switch, and while it is on the questions of its variants.
    // `picked` is the set the sheet started from, which a switch turned on again reads its values from.
    let {
        row,
        sheet,
        picked,
        disabled,
        onchange,
    }: {
        row: RuleRow;
        sheet: Options;
        picked: Options;
        disabled: boolean;
        onchange: (next: Options) => void;
    } = $props();

    const NAMES: Record<RuleRow, { name: string; line: string }> = {
        points: { name: words["start.rulePoints"], line: words["start.rulePointsLine"] },
        kontra: { name: words["start.ruleKontra"], line: words["start.ruleKontraLine"] },
        ramsch: { name: words["start.ruleRamsch"], line: words["start.ruleRamschLine"] },
        pushing: { name: words["start.rulePushing"], line: words["start.rulePushingLine"] },
        bock: { name: words["start.ruleBock"], line: words["start.ruleBockLine"] },
    };
    const { name, line } = $derived(NAMES[row]);
    const on = $derived(isOn(sheet, row));
    const questions = $derived(QUESTIONS.filter((each) => each.rule === row));
</script>

<div class="unit" class:sub={row === "pushing"}>
    <button
        type="button"
        class="rule"
        class:on
        role="switch"
        aria-checked={on}
        aria-label={name}
        {disabled}
        onclick={() => {
            onchange(switchRule(sheet, row, !on, picked));
        }}
    >
        <span class="ic"><RuleMark id={row} /></span>
        <span class="txt">
            <b>{name}</b>
            <small>{line}</small>
        </span>
        <span class="sw" aria-hidden="true">
            <i>
                <RuleMark id="official" />
            </i>
        </span>
    </button>
    {#if on}
        <div class="vars">
            {#if row === "bock"}
                <div class="ask" role="group" aria-label={words["start.askBockTriggers"]}>
                    <span class="q">{words["start.askBockTriggers"]}</span>
                    <div class="flags">
                        {#each TRIGGER_SWITCHES as trigger (trigger.token)}
                            {@const flagged = triggerOn(sheet, trigger.token)}
                            <button
                                type="button"
                                class="flag"
                                class:on={flagged}
                                role="switch"
                                aria-checked={flagged}
                                {disabled}
                                onclick={() => {
                                    onchange(toggleTrigger(sheet, trigger.token));
                                }}
                            >
                                <span>{trigger.word}</span>
                                <span class="sw sm" aria-hidden="true">
                                    <i>
                                        <RuleMark id="official" />
                                    </i>
                                </span>
                            </button>
                        {/each}
                    </div>
                </div>
            {/if}
            {#each questions as asked (asked.id)}
                <div class="ask" role="radiogroup" aria-label={asked.text}>
                    <span class="q">{asked.text}</span>
                    <div class="pick">
                        {#each asked.pills as pill (pill.token)}
                            {@const chosen = asked.picked(sheet) === pill.token}
                            <label class="pk" class:on={chosen}>
                                <input
                                    type="radio"
                                    name={asked.id}
                                    checked={chosen}
                                    {disabled}
                                    onchange={() => {
                                        onchange(pill.apply(sheet));
                                    }}
                                />
                                {#if chosen}
                                    <RuleMark id="official" />
                                {/if}
                                <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {pill.word} compiles to a `?? ""` branch no pill can take -->
                                {`${pill.word}`}
                            </label>
                        {/each}
                    </div>
                </div>
            {/each}
        </div>
    {/if}
</div>
