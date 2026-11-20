<script lang="ts">
    import { untrack } from "svelte";
    import { RULE_SET_NAME_MAX, SERIES_LENGTH_MAX, SERIES_LENGTH_MIN, SERIES_LENGTH_STEP } from "#lib/wire.ts";
    import RuleMark from "#lib/ui/RuleMark.svelte";
    import { words } from "#lib/words.ts";
    import { differs, isOn, OFFICIAL, requestOf, suggestedName } from "./openingRules.ts";
    import RuleUnit from "./RuleUnit.svelte";
    import { readRuleSets, saveRuleSet, type RuleSet } from "./openTable.ts";
    import type { Options } from "./tables.ts";

    // The settings of a series, as the sheet that opens a table and the one that changes the next series' show them: its
    // length, the rule sets the person saved, the rules with their variants and the way to save them as a set. The
    // sheet's own head and buttons stay with the caller, which is told by `onchange` when the length or the rules change.
    let {
        length = $bindable(),
        sheet = $bindable(),
        disabled,
        onchange,
    }: { length: number; sheet: Options; disabled: boolean; onchange: () => void } = $props();

    // The person's own sets, read when the sheet opens; the official rules are no set and always offered.
    let sets = $state<RuleSet[]>([]);
    let setsUnreadable = $state(false);
    // A sheet that opens with other rules than the official ones, as the next series' last ones, has no rule set chosen,
    // and a rule switched back on there reads its values from the rules the sheet came with.
    const startOptions = untrack(() => sheet);
    let picked = $state<RuleSet | "official" | "none">(untrack(() => (differs(sheet, OFFICIAL) ? "none" : "official")));
    // The name the person typed over the suggested one; null while the suggestion stands.
    let typedName = $state<string | null>(null);
    let saving = $state(false);
    let saveProblem = $state<"taken" | "failed" | null>(null);
    let scrolledDown = $state(false);
    let scrolledUp = $state(false);

    // What a rule switched on again takes its values from, and what the sheet must differ from to offer the save.
    const pickedOptions = $derived(
        picked === "none" ? startOptions : picked === "official" ? OFFICIAL : picked.options,
    );
    const offered = $derived(differs(sheet, pickedOptions));
    const setName = $derived(typeof picked === "object" ? picked.name : words["start.setOfficial"]);
    const name = $derived(typedName ?? suggestedName(setName, sheet, picked === "none" ? OFFICIAL : pickedOptions));
    const rows = $derived(
        (["points", "kontra", "ramsch", "pushing", "bock", "giveUpPartner", "giveUpAnyTime"] as const).filter(
            (row) => row !== "pushing" || isOn(sheet, "ramsch"),
        ),
    );

    $effect(() => {
        let reading = true;
        void readRuleSets().then((outcome) => {
            if (!reading) return;
            sets = outcome.kind === "sets" ? outcome.sets : [];
            setsUnreadable = outcome.kind === "failed";
        });
        return () => {
            reading = false;
        };
    });

    function show(next: Options): void {
        if (differs(next, sheet)) onchange();
        sheet = next;
        saveProblem = null;
    }

    function setLength(next: number): void {
        if (next === length) return;
        length = next;
        onchange();
    }

    // A pick replaces whatever was changed on the sheet.
    function pick(set: RuleSet | "official"): void {
        picked = set;
        typedName = null;
        show(set === "official" ? OFFICIAL : set.options);
    }

    function isPicked(set: RuleSet): boolean {
        return typeof picked === "object" && picked.id === set.id;
    }

    function byNameThenId(left: RuleSet, right: RuleSet): number {
        const [leftKey, rightKey] = [
            `${left.name.toLowerCase()}\0${left.id}`,
            `${right.name.toLowerCase()}\0${right.id}`,
        ];
        return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
    }

    // The saved set is picked, so the sheet shows exactly what the set holds.
    async function save(): Promise<void> {
        saving = true;
        saveProblem = null;
        const outcome = await saveRuleSet(name, requestOf(sheet));
        saving = false;
        if (outcome.kind !== "saved") {
            saveProblem = outcome.kind;
            return;
        }
        // The server lists sets by name without regard to case, then by id. A list read that already holds the set
        // is replaced by the saved one, so the set stays offered once.
        sets = [...sets.filter((each) => each.id !== outcome.set.id), outcome.set].sort(byNameThenId);
        pick(outcome.set);
    }

    function step(by: number): void {
        setLength(length + by);
    }

    // The rules scroll beneath the fixed head and buttons; a fade shows where more of them lie.
    function fades(node: HTMLElement): { destroy: () => void } {
        const update = (): void => {
            scrolledUp = node.scrollTop > 0;
            scrolledDown = node.scrollTop + node.clientHeight < node.scrollHeight - 1;
        };
        const observer = new ResizeObserver(update);
        observer.observe(node);
        for (const child of node.children) observer.observe(child);
        node.addEventListener("scroll", update);
        return {
            destroy: () => {
                observer.disconnect();
                node.removeEventListener("scroll", update);
            },
        };
    }
</script>

<div class="stepper" role="group" aria-label={words["start.seriesLength"]}>
    <button
        type="button"
        class="step"
        aria-label={words["start.seriesFewer"]}
        disabled={length <= SERIES_LENGTH_MIN || disabled}
        onclick={() => {
            step(-SERIES_LENGTH_STEP);
        }}
    >
        −
    </button>
    <span
        class="value"
        role="spinbutton"
        tabindex="0"
        aria-valuemin={SERIES_LENGTH_MIN}
        aria-valuemax={SERIES_LENGTH_MAX}
        aria-valuenow={length}
        aria-label={words["start.seriesGames"](length)}
    >
        {length}<small>{words["start.seriesGames"](length)}</small>
    </span>
    <button
        type="button"
        class="step"
        aria-label={words["start.seriesMore"]}
        disabled={length >= SERIES_LENGTH_MAX || disabled}
        onclick={() => {
            step(SERIES_LENGTH_STEP);
        }}
    >
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.6"
            stroke-linecap="round"
            aria-hidden="true"
        >
            <path d="M12 5v14M5 12h14" />
        </svg>
    </button>
</div>
<div class="sets" role="radiogroup" aria-label={words["start.ruleSets"]}>
    <label class="set" class:on={picked === "official"}>
        <input
            type="radio"
            name="rule-set"
            checked={picked === "official"}
            disabled={disabled || saving}
            onchange={() => {
                pick("official");
            }}
        />
        {#if picked === "official"}<RuleMark id="official" />{/if}
        <span class="name">{words["start.setOfficial"]}</span>
    </label>
    {#each sets as set (set.id)}
        <label class="set" class:on={isPicked(set)}>
            <input
                type="radio"
                name="rule-set"
                checked={isPicked(set)}
                disabled={disabled || saving}
                onchange={() => {
                    pick(set);
                }}
            />
            {#if isPicked(set)}<RuleMark id="official" />{/if}
            <span class="name">{set.name}</span>
        </label>
    {/each}
</div>
{#if setsUnreadable}
    <p role="status">{words["start.setsUnreadable"]}</p>
{/if}
<div class="sheet-body" class:up={scrolledUp} class:down={scrolledDown} use:fades>
    <div class="rules">
        {#each rows as row (row)}
            <RuleUnit {row} {sheet} picked={pickedOptions} disabled={disabled || saving} onchange={show} />
        {/each}
    </div>
</div>
{#if offered}
    <div class="save" role="group" aria-label={words["start.saveRules"]}>
        <span class="ic" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">
                <path d="M12 5v14M5 12h14" />
            </svg>
        </span>
        <span class="txt">
            <button type="button" class="go" disabled={disabled || saving} onclick={save}>
                {words["start.saveRules"]}
            </button>
            <textarea
                class="name"
                rows="1"
                aria-label={words["start.saveName"]}
                maxlength={RULE_SET_NAME_MAX}
                value={name}
                disabled={disabled || saving}
                onkeydown={(event) => {
                    if (event.key === "Enter") event.preventDefault();
                }}
                oninput={(event) => {
                    typedName = event.currentTarget.value.replace(/\s*\n\s*/g, " ");
                    saveProblem = null;
                }}></textarea>
            {#if saveProblem !== null}
                <small role="alert">
                    {saveProblem === "taken" ? words["start.saveNameTaken"] : words["start.saveFailed"]}
                </small>
            {/if}
        </span>
    </div>
{/if}
