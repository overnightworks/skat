import type { Options } from "../routes/(start)/tables.ts";
import {
    BOCK_OVERLAP_TOKENS,
    BOCK_TRIGGER_TOKENS,
    DURCHMARSCH_TOKENS,
    GRAND_HAND_TOKENS,
    JUNGFRAU_TOKENS,
    KONTRA_DEADLINE_TOKENS,
    KONTRA_REACH_TOKENS,
    KONTRA_SAYER_TOKENS,
    PUSHING_RULE_TOKENS,
    RAMSCH_SCORING_TOKENS,
} from "#lib/wire.ts";
import { language, words } from "#lib/words.ts";

type Token<Tokens extends readonly string[]> = Tokens[number];

export type RuleId = "points" | "kontra" | "ramsch" | "pushing" | "bock";
// A chip stands for one rule that is on; the table without any carries the one chip of the official rules.
export type ChipId = Exclude<RuleId, "pushing"> | "official";
export type RuleChip = { id: ChipId; word: string };
// A rule's settings are separate short texts, never one sentence.
export type RuleRow = { id: RuleId; name: string; settings: string[] };
export type TableRules = { chips: RuleChip[]; rows: RuleRow[] };

const KONTRA_SAYER_WORDS: Record<Token<typeof KONTRA_SAYER_TOKENS>, string> = {
    "any-opponent": words["rules.kontraSayerAnyOpponent"],
    "bidders-only": words["rules.kontraSayerBiddersOnly"],
};
const KONTRA_REACH_WORDS: Record<Token<typeof KONTRA_REACH_TOKENS>, string> = {
    "kontra-re": words["rules.kontraReachKontraRe"],
    "kontra-re-standings": words["rules.kontraReachKontraReStandings"],
    "up-to-hirsch": words["rules.kontraReachUpToHirsch"],
};
const KONTRA_DEADLINE_WORDS: Record<Token<typeof KONTRA_DEADLINE_TOKENS>, string> = {
    "own-card": words["rules.kontraDeadlineOwnCard"],
    "first-card": words["rules.kontraDeadlineFirstCard"],
};
const RAMSCH_SCORING_WORDS: Record<Token<typeof RAMSCH_SCORING_TOKENS>, string> = {
    points: words["rules.ramschScoringPoints"],
    "points-by-ten": words["rules.ramschScoringPointsByTen"],
    "skat-to-loser": words["rules.ramschScoringSkatToLoser"],
};
const JUNGFRAU_WORDS: Record<Token<typeof JUNGFRAU_TOKENS>, string> = {
    "doubles-loser": words["rules.jungfrauDoublesLoser"],
    off: words["rules.jungfrauOff"],
};
const DURCHMARSCH_WORDS: Record<Token<typeof DURCHMARSCH_TOKENS>, string> = {
    "wins-120": words["rules.durchmarschWins120"],
    "wins-120-flat": words["rules.durchmarschWins120Flat"],
    off: words["rules.durchmarschOff"],
};
const PUSHING_RULE_WORDS: Record<Token<typeof PUSHING_RULE_TOKENS>, string> = {
    "jacks-stay": words["rules.pushingJacksStay"],
    "jacks-may-go": words["rules.pushingJacksMayGo"],
    "no-doubling": words["rules.pushingNoDoubling"],
};
// A table that does not allow a Grand Hand says nothing about it.
const GRAND_HAND_WORDS: Record<Token<typeof GRAND_HAND_TOKENS>, string | null> = {
    allowed: words["rules.grandHandAllowed"],
    off: null,
};
const BOCK_TRIGGER_WORDS: Record<Token<typeof BOCK_TRIGGER_TOKENS>, string> = {
    "sixty-sixty": words["rules.bockTriggerSixtySixty"],
    "won-grand-hand": words["rules.bockTriggerWonGrandHand"],
    "lost-after-kontra": words["rules.bockTriggerLostAfterKontra"],
    re: words["rules.bockTriggerRe"],
    "passed-in": words["rules.bockTriggerPassedIn"],
    schneider: words["rules.bockTriggerSchneider"],
    schwarz: words["rules.bockTriggerSchwarz"],
    "total-ending-in-00": words["rules.bockTriggerTotalEndingIn00"],
};
const BOCK_OVERLAP_WORDS: Record<Token<typeof BOCK_OVERLAP_TOKENS>, string> = {
    append: words["rules.bockOverlapAppend"],
    multiply: words["rules.bockOverlapMultiply"],
    ignore: words["rules.bockOverlapIgnore"],
};

const CHIP_WORDS: Record<ChipId, string> = {
    points: words["rules.chipPoints"],
    kontra: words["rules.chipKontra"],
    ramsch: words["rules.chipRamsch"],
    bock: words["rules.chipBock"],
    official: words["rules.chipOfficial"],
};

const triggerList = new Intl.ListFormat(language, { style: "long", type: "conjunction" });

// The rules that are on, in the order the picture draws them.
function rulesOf(options: Options): RuleRow[] {
    const { kontra, ramsch, bock } = options;
    const rules: (RuleRow | null)[] = [
        options.show_running_points
            ? { id: "points", name: words["rules.namePoints"], settings: [words["rules.pointsFromTricks"]] }
            : null,
        kontra === null
            ? null
            : {
                  id: "kontra",
                  name: words["rules.nameKontra"],
                  settings: [
                      KONTRA_SAYER_WORDS[kontra.sayer],
                      KONTRA_REACH_WORDS[kontra.reach],
                      KONTRA_DEADLINE_WORDS[kontra.deadline],
                  ],
              },
        ramsch === null
            ? null
            : {
                  id: "ramsch",
                  name: words["rules.nameRamsch"],
                  settings: [
                      RAMSCH_SCORING_WORDS[ramsch.scoring],
                      JUNGFRAU_WORDS[ramsch.jungfrau],
                      DURCHMARSCH_WORDS[ramsch.durchmarsch],
                  ],
              },
        ramsch?.pushing == null
            ? null
            : {
                  id: "pushing",
                  name: words["rules.namePushing"],
                  settings: [
                      PUSHING_RULE_WORDS[ramsch.pushing.rule],
                      GRAND_HAND_WORDS[ramsch.pushing.grand_hand],
                  ].filter((setting) => setting !== null),
              },
        bock === null
            ? null
            : {
                  id: "bock",
                  name: words["rules.nameBock"],
                  settings: [
                      words["rules.bockTriggers"]({
                          triggers: triggerList.format(bock.triggers.map((trigger) => BOCK_TRIGGER_WORDS[trigger])),
                      }),
                      BOCK_OVERLAP_WORDS[bock.overlap],
                  ],
              },
    ];
    return rules.filter((rule) => rule !== null);
}

// What every viewer reads of a table's rules: the chips on the felt and the rows of the sheet behind them.
export function tableRules(options: Options): TableRules {
    const rows = rulesOf(options);
    const chipIds = rows.map((row) => row.id).filter((id) => id !== "pushing");
    return {
        chips: (chipIds.length === 0 ? (["official"] as const) : chipIds).map((id) => ({ id, word: CHIP_WORDS[id] })),
        rows,
    };
}
