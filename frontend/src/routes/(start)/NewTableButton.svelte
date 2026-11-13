<script lang="ts">
    import { goto } from "$app/navigation";
    import { resolve } from "$app/paths";
    import {
        RULE_SET_NAME_MAX,
        SERIES_LENGTH_DEFAULT,
        SERIES_LENGTH_MAX,
        SERIES_LENGTH_MIN,
        SERIES_LENGTH_STEP,
    } from "#lib/wire.ts";
    import RuleMark from "#lib/ui/RuleMark.svelte";
    import { words } from "#lib/words.ts";
    import { differs, isOn, OFFICIAL, requestOf, suggestedName } from "./openingRules.ts";
    import RuleUnit from "./RuleUnit.svelte";
    import { createTable, readRuleSets, saveRuleSet, type Options, type RuleSet } from "./tables.ts";

    let choosing = $state(false);
    let length = $state(SERIES_LENGTH_DEFAULT);
    // The person's own sets, read each time the sheet opens; the official rules are no set and always offered.
    let sets = $state<RuleSet[]>([]);
    let setsUnreadable = $state(false);
    let picked = $state<RuleSet | null>(null);
    let sheet = $state(OFFICIAL);
    let opening = $state(false);
    let failed = $state(false);
    // The name the person typed over the suggested one; null while the suggestion stands.
    let typedName = $state<string | null>(null);
    let saving = $state(false);
    let saveProblem = $state<"taken" | "failed" | null>(null);
    let commandId = crypto.randomUUID();
    let openings = 0;
    let scrolledDown = $state(false);
    let scrolledUp = $state(false);

    const pickedOptions = $derived(picked?.options ?? OFFICIAL);
    const offered = $derived(differs(sheet, pickedOptions));
    const name = $derived(typedName ?? suggestedName(picked?.name ?? words["start.setOfficial"], sheet, pickedOptions));
    const rows = $derived(
        (["points", "kontra", "ramsch", "pushing", "bock"] as const).filter(
            (row) => row !== "pushing" || isOn(sheet, "ramsch"),
        ),
    );

    // Another length or another request is another command, so a retry never sends two requests under one id,
    // and a sheet that shows what was asked before keeps its id, so a lost answer is replayed, not duplicated.
    function changed(): void {
        commandId = crypto.randomUUID();
    }

    function show(next: Options): void {
        if (differs(next, sheet)) changed();
        sheet = next;
        saveProblem = null;
    }

    async function choose(): Promise<void> {
        failed = false;
        setLength(SERIES_LENGTH_DEFAULT);
        pick(null);
        sets = [];
        setsUnreadable = false;
        choosing = true;
        const opened = ++openings;
        const outcome = await readRuleSets();
        if (opened !== openings) return;
        sets = outcome.kind === "sets" ? outcome.sets : [];
        setsUnreadable = outcome.kind === "failed";
    }

    function setLength(next: number): void {
        if (next === length) return;
        length = next;
        changed();
    }

    // A pick replaces whatever was changed on the sheet.
    function pick(set: RuleSet | null): void {
        picked = set;
        typedName = null;
        show(set?.options ?? OFFICIAL);
    }

    // The saved set is picked, so the sheet shows exactly what the set holds.
    async function save(): Promise<void> {
        saving = true;
        saveProblem = null;
        const opened = openings;
        const outcome = await saveRuleSet(name, requestOf(sheet));
        saving = false;
        if (opened !== openings) return;
        if (outcome.kind !== "saved") {
            saveProblem = outcome.kind;
            return;
        }
        if (!sets.some((each) => each.id === outcome.set.id)) sets = [...sets, outcome.set];
        pick(outcome.set);
    }

    function step(by: number): void {
        setLength(length + by);
    }

    function close(): void {
        choosing = false;
        openings++;
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

    async function open(): Promise<void> {
        opening = true;
        const outcome = await createTable(commandId, length, requestOf(sheet));
        opening = false;
        failed = outcome.kind !== "table";
        if (outcome.kind === "table") {
            // The next table is another command, even when the browser restores this page from its cache.
            commandId = crypto.randomUUID();
            choosing = false;
            await goto(resolve("/(start)/t/[id]", { id: outcome.table.id }));
        }
    }
</script>

<div class="new-table">
    <button type="button" onclick={choose}>
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
        {`${words["start.newTable"]}`}
    </button>
</div>
{#if choosing}
    <div class="scrim"></div>
    <div class="sheet" role="dialog" aria-modal="true" aria-label={words["start.newTable"]}>
        <h3>{words["start.newTable"]}</h3>
        <div class="stepper" role="group" aria-label={words["start.seriesLength"]}>
            <button
                type="button"
                class="step"
                aria-label={words["start.seriesFewer"]}
                disabled={length <= SERIES_LENGTH_MIN || opening}
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
                disabled={length >= SERIES_LENGTH_MAX || opening}
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
            <label class="set" class:on={picked === null}>
                <input
                    type="radio"
                    name="rule-set"
                    checked={picked === null}
                    disabled={opening}
                    onchange={() => {
                        pick(null);
                    }}
                />
                {#if picked === null}<RuleMark id="official" />{/if}
                {words["start.setOfficial"]}
            </label>
            {#each sets as set (set.id)}
                <label class="set" class:on={picked?.id === set.id}>
                    <input
                        type="radio"
                        name="rule-set"
                        checked={picked?.id === set.id}
                        disabled={opening}
                        onchange={() => {
                            pick(set);
                        }}
                    />
                    {#if picked?.id === set.id}<RuleMark id="official" />{/if}
                    {set.name}
                </label>
            {/each}
        </div>
        {#if setsUnreadable}
            <p role="status">{words["start.setsUnreadable"]}</p>
        {/if}
        <div class="sheet-body" class:up={scrolledUp} class:down={scrolledDown} use:fades>
            <div class="rules">
                {#each rows as row (row)}
                    <RuleUnit {row} {sheet} picked={pickedOptions} disabled={opening} onchange={show} />
                {/each}
            </div>
        </div>
        {#if offered}
            <div class="save" role="group" aria-label={words["start.saveRules"]}>
                <span class="ic" aria-hidden="true">
                    <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.6"
                        stroke-linecap="round"
                    >
                        <path d="M12 5v14M5 12h14" />
                    </svg>
                </span>
                <span class="txt">
                    <button type="button" class="go" disabled={opening || saving} onclick={save}>
                        {words["start.saveRules"]}
                    </button>
                    <input
                        class="name"
                        type="text"
                        aria-label={words["start.saveName"]}
                        maxlength={RULE_SET_NAME_MAX}
                        value={name}
                        disabled={opening || saving}
                        oninput={(event) => {
                            typedName = event.currentTarget.value;
                            saveProblem = null;
                        }}
                    />
                    {#if saveProblem !== null}
                        <small role="alert">
                            {saveProblem === "taken" ? words["start.saveNameTaken"] : words["start.saveFailed"]}
                        </small>
                    {/if}
                </span>
            </div>
        {/if}
        {#if failed}
            <p role="alert">{words["start.newTableFailed"]}</p>
        {/if}
        <div class="btns">
            <button type="button" class="confirm" disabled={opening} onclick={open}>
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
                {`${words["start.openTable"]}`}
            </button>
            <button type="button" class="cancel" disabled={opening} onclick={close}>
                {words["start.cancelNewTable"]}
            </button>
        </div>
    </div>
{/if}
