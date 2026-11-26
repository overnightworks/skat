// Generated from the Python path and token owners by scripts/generate_wire.py. Do not edit.

export const AUTH_START_PATH = "/auth/start";
export const RETURN_PATH_QUERY_NAME = "next";
export const SIGNED_IN_AGAIN_QUERY_NAME = "signedInAgain";
export const NO_ACCESS_PATH = "/no-access";
export const CALL_SIGN_IN_PATH = "/login/call";
export const MODE_QUERY_NAME = "mode";
export const CALL_MODE = "call";
export const LOGOUT_PATH = "/logout";
export const ACCOUNT_PATH = "/api/account";
export const VERSION_FILE_PATH = "/_app/version.json";
export const CALL_ORIGIN_PATH = "/api/call-origin";
export const ACCOUNT_CONSOLE_PATH = "/account";
export const TABLES_PATH = "/api/tables";
export const RULE_SETS_PATH = "/api/rule-sets";
export const LOBBY_EVENTS_PATH = "/api/lobby/events";
export const TABLE_PAGE_PREFIX = "/t/";
export const TABLE_ID_PATTERN = "[0-9a-f]{32}";
export const TABLE_EVENTS_SUFFIX = "/events";
export const TABLE_SIT_SUFFIX = "/sit";
export const TABLE_STAND_SUFFIX = "/stand";
export const TABLE_STOP_PLAYING_SUFFIX = "/stop-playing";
export const TABLE_DECLARING_TAKE_SUFFIX = "/declaring/take";
export const TABLE_DECLARING_PUT_BACK_SUFFIX = "/declaring/put-back";
export const TABLE_DECLARING_DECLARE_SUFFIX = "/declaring/declare";
export const TABLE_PUSHING_TAKE_SUFFIX = "/pushing/take";
export const TABLE_PUSHING_PUT_BACK_SUFFIX = "/pushing/put-back";
export const TABLE_PUSHING_PUSH_SUFFIX = "/pushing/push";
export const TABLE_PUSHING_GRAND_HAND_SUFFIX = "/pushing/grand-hand";
export const TABLE_AUCTION_BID_SUFFIX = "/auction/bid";
export const TABLE_AUCTION_HOLD_SUFFIX = "/auction/hold";
export const TABLE_AUCTION_PASS_SUFFIX = "/auction/pass";
export const TABLE_AUCTION_PLAN_SUFFIX = "/auction/plan";
export const TABLE_AUCTION_PLAY_SUFFIX = "/auction/play";
export const TABLE_CARD_SUFFIX = "/card";
export const TABLE_GIVE_UP_SUFFIX = "/give-up";
export const TABLE_GIVE_UP_AGREE_SUFFIX = "/give-up/agree";
export const TABLE_GIVE_UP_DECLINE_SUFFIX = "/give-up/decline";
export const TABLE_SHORTEN_SUFFIX = "/shorten";
export const TABLE_PLAY_OPEN_SUFFIX = "/play-open";
export const TABLE_LIST_SUFFIX = "/list";
export const TABLE_KONTRA_SUFFIX = "/kontra";
export const TABLE_NO_WORD_SUFFIX = "/kontra/no-word";
export const TABLE_READY_SUFFIX = "/ready";
export const TABLE_NEW_SERIES_SUFFIX = "/new-series";
export const TABLE_NEXT_SETTINGS_SUFFIX = "/next-settings";
export const TABLE_STYLE_SUFFIX = "/style";
export const TABLE_SERIES_END_AGREE_SUFFIX = "/series-end/agree";
export const TABLE_SERIES_END_REFUSE_SUFFIX = "/series-end/refuse";
export const TABLE_AGENTS_SUFFIX = "/agents";
export const TABLE_AGENT_CALL_SUFFIX = "/call";
export const TABLE_AGENT_SEND_AWAY_SUFFIX = "/send-away";
export const TABLE_ABORT_AGREE_SUFFIX = "/abort/agree";
export const TABLE_ABORT_REFUSE_SUFFIX = "/abort/refuse";
export const TABLE_NUDGE_SUFFIX = "/nudge";
export const TABLE_REACTION_SUFFIX = "/reaction";
export const TABLE_PERSON_KEYS_SUFFIX = "/person-keys";
export const SUIT_TOKENS = ["kreuz", "pik", "herz", "karo"] as const;
export const RANK_TOKENS = ["seven", "eight", "nine", "ten", "jack", "queen", "king", "ace"] as const;
export const POSITION_TOKENS = ["forehand", "middlehand", "rearhand"] as const;
export const GAME_TOKENS = ["karo", "herz", "pik", "kreuz", "grand", "null"] as const;
export const ANNOUNCEMENT_TOKENS = ["none", "schneider", "schwarz"] as const;
export const STAGE_TOKENS = ["choosing", "discarding", "picked", "declared"] as const;
export const AWAITING_TOKENS = ["bid", "answer", "play"] as const;
export const AUCTION_ACTION_TOKENS = ["bid", "hold", "pass", "play"] as const;
export const PLAN_KIND_TOKENS = ["limit", "pass"] as const;
export const PLAN_MODE_TOKENS = ["fixed", "ask"] as const;
export const LEVEL_TOKENS = [
    "spiel",
    "hand",
    "schneider",
    "schneider_announced",
    "schwarz",
    "schwarz_announced",
    "ouvert",
] as const;
export const END_REASON_TOKENS = ["empty", "unplayed", "closed"] as const;
export const KONTRA_SAYER_TOKENS = ["any-opponent", "bidders-only"] as const;
export const KONTRA_REACH_TOKENS = ["kontra-re", "kontra-re-standings", "up-to-hirsch"] as const;
export const KONTRA_DEADLINE_TOKENS = ["own-card", "first-card"] as const;
export const BOCK_TRIGGER_TOKENS = [
    "sixty-sixty",
    "won-grand-hand",
    "lost-after-kontra",
    "re",
    "passed-in",
    "schneider",
    "schwarz",
    "total-ending-in-00",
] as const;
export const BOCK_OVERLAP_TOKENS = ["append", "multiply", "ignore"] as const;
export const RAMSCH_OCCASION_TOKENS = ["passed-in", "bock-rounds", "passed-in-and-bock-rounds"] as const;
export const RAMSCH_SCORING_TOKENS = ["points", "points-by-ten", "skat-to-loser"] as const;
export const JUNGFRAU_TOKENS = ["doubles-loser", "off"] as const;
export const DURCHMARSCH_TOKENS = ["wins-120", "wins-120-flat", "off"] as const;
export const PUSHING_RULE_TOKENS = ["jacks-stay", "jacks-may-go", "no-doubling"] as const;
export const GRAND_HAND_TOKENS = ["allowed", "off"] as const;
export const WAITING_CASE_TOKENS = ["turn", "give_up", "kontra", "end_proposal", "result", "series_end"] as const;
export const GAME_ENDING_TOKENS = ["played-out", "given-up", "thrown-down", "shortened", "played-open"] as const;
export const WORD_TOKENS = ["kontra", "re", "supra", "hirsch"] as const;
export const VISIBILITY_TOKENS = ["open", "private"] as const;
export const TABLE_STYLE_TOKENS = ["klassik", "strandbar"] as const;
export const REACTION_TOKENS = [
    "clap",
    "laugh",
    "gasp",
    "fire",
    "cheers",
    "knock",
    "cocktail",
    "shell",
    "coaster",
    "lamp",
] as const;
export const OCCUPANT_KIND_TOKENS = ["person", "agent"] as const;
export const STOP_OUTCOME_TOKENS = ["not_enabled", "busy", "budget_spent", "unavailable"] as const;
export const PUSH_ACTION_TOKENS = ["took", "pushed"] as const;
export const CARD_STATE_TOKENS = ["played", "put-away", "unplayed"] as const;
export const RULE_SET_REFUSAL_TOKENS = ["name-taken"] as const;
export const REFUSAL_TOKENS = [
    "seat-taken",
    "already-seated",
    "not-seated",
    "hand-running",
    "no-hand",
    "stale-version",
    "wrong-phase",
    "not-declarer",
    "no-request",
    "already-answered",
    "request-pending",
    "no-result",
    "stale-result",
    "stale-series",
    "stale-settings",
    "series-over",
    "no-series",
    "series-not-over",
    "no-game-yet",
    "no-proposal",
    "end-refused",
    "rule-off",
    "not-an-agent",
    "seat-open",
    "own-seat-only",
    "answer-time-over",
    "not-allowed",
    "hand-not-open",
] as const;
export const BID_REFUSAL_TOKENS = [
    "over",
    "already-passed",
    "not-your-turn",
    "wrong-action",
    "invalid-value",
    "not-above-standing",
] as const;
export const DECLARATION_REFUSAL_TOKENS = [
    "already-declared",
    "out-of-order",
    "not-two-of-the-twelve",
    "level-not-allowed-after-pick-up",
    "announcement-in-null",
] as const;
export const PLAY_REFUSAL_TOKENS = [
    "over",
    "not-your-turn",
    "not-in-hand",
    "must-follow",
    "claim-out-of-reach",
    "needs-consent",
    "not-an-opponent",
] as const;
export const KONTRA_REFUSAL_TOKENS = [
    "over",
    "beyond-reach",
    "not-your-word",
    "did-not-bid",
    "too-late",
    "words-due",
] as const;
export const PUSH_REFUSAL_TOKENS = [
    "over",
    "not-your-turn",
    "out-of-order",
    "grand-hand-off",
    "not-two-of-the-twelve",
    "jack-put-back",
] as const;
export const NUDGE_REFUSAL_TOKENS = [
    "not-seated",
    "stale-version",
    "seat-open",
    "not-waiting",
    "own-seat",
    "away",
    "too-early",
    "already-nudged",
] as const;
export const REACTION_REFUSAL_TOKENS = ["not-at-the-table", "too-fast"] as const;
export const VALID_BIDS = [
    18, 20, 22, 23, 24, 27, 30, 33, 35, 36, 40, 44, 45, 46, 48, 50, 54, 55, 59, 60, 63, 66, 70, 72, 77, 80, 81, 84, 88,
    90, 96, 99, 100, 108, 110, 117, 120, 121, 126, 130, 132, 135, 140, 143, 144, 150, 153, 154, 156, 160, 162, 165, 168,
    170, 176, 180, 187, 192, 198, 204, 216, 240, 264,
] as const;
export const ALL_POINTS = 120;
export const SERIES_LENGTH_MIN = 3;
export const SERIES_LENGTH_MAX = 99;
export const SERIES_LENGTH_STEP = 3;
export const SERIES_LENGTH_DEFAULT = 36;
export const CHAIRS_PER_TABLE = 3;
export const ASK_AGAIN_AFTER = 60;
export const RULE_SET_NAME_MAX = 40;
export const STREAM_HEARTBEAT_SECONDS = 15;
export const SWITCH_ON_OPTIONS = {
    show_running_points: false,
    kontra: {
        sayer: "bidders-only",
        reach: "up-to-hirsch",
        deadline: "own-card",
    },
    bock: {
        triggers: ["sixty-sixty", "won-grand-hand", "lost-after-kontra", "re"],
        overlap: "append",
    },
    ramsch: {
        occasion: "passed-in",
        scoring: "points",
        jungfrau: "doubles-loser",
        durchmarsch: "wins-120",
        pushing: {
            rule: "jacks-stay",
            grand_hand: "off",
        },
    },
    give_up: {
        partner_agrees: false,
        any_time: false,
    },
} as const;
export type AccountName = {
    name: string;
};
export type AuctionAnswer = {
    turn_seat: number | null;
    facing_seat: number | null;
    awaiting: (typeof AWAITING_TOKENS)[number] | null;
    standing: number | null;
    values: number[];
    words: AuctionWordAnswer[];
    steps: AuctionWordAnswer[];
    declared: AuctionDeclaredAnswer | null;
    plan: AuctionPlanAnswer | null;
    hand_values: HandValueAnswer[];
};
export type AuctionDeclaredAnswer = {
    seat: number;
    value: number;
};
export type AuctionPlanAnswer = {
    kind: (typeof PLAN_KIND_TOKENS)[number];
    value: number | null;
    mode: (typeof PLAN_MODE_TOKENS)[number] | null;
};
export type AuctionWordAnswer = {
    seat: number;
    action: (typeof AUCTION_ACTION_TOKENS)[number];
    value: number | null;
};
export type BockAnswer = {
    games_left: number;
    factor: number;
};
export type BockOptionsAnswer = {
    triggers: (typeof BOCK_TRIGGER_TOKENS)[number][];
    overlap: (typeof BOCK_OVERLAP_TOKENS)[number];
};
export type CallOrigin = {
    origin: string | null;
};
export type CardAnswer = {
    suit: (typeof SUIT_TOKENS)[number];
    rank: (typeof RANK_TOKENS)[number];
};
export type ChairAnswer = {
    seat: number;
    occupant_name: string | null;
    occupant_kind: (typeof OCCUPANT_KIND_TOKENS)[number] | null;
    is_mine: boolean;
    is_away: boolean;
    ready: boolean;
    hand: ChairHandAnswer | null;
    total: number | null;
    former_holder_name: string | null;
    is_mine_to_return: boolean;
    nudge: NudgeAnswer | null;
    turn_state: TurnStateAnswer | null;
};
export type ChairHandAnswer = {
    position: (typeof POSITION_TOKENS)[number];
    card_count: number;
};
export type ClosedNoGamesAnswer = {
    reason: "closed";
    empty_seconds: null;
    unplayed_days: null;
    closed_by_name: string | null;
    standings: null;
    game_count: null;
};
export type ClosedWithGamesAnswer = {
    reason: "closed";
    empty_seconds: null;
    unplayed_days: null;
    closed_by_name: null;
    standings: StandingAnswer[];
    game_count: number;
};
export type CommandRefusal =
    | (typeof REFUSAL_TOKENS)[number]
    | (typeof BID_REFUSAL_TOKENS)[number]
    | (typeof DECLARATION_REFUSAL_TOKENS)[number]
    | (typeof PLAY_REFUSAL_TOKENS)[number]
    | (typeof KONTRA_REFUSAL_TOKENS)[number]
    | (typeof PUSH_REFUSAL_TOKENS)[number];
export type DeclarationAnswer = {
    game: (typeof GAME_TOKENS)[number];
    hand: boolean;
    ouvert: boolean;
    announcement: (typeof ANNOUNCEMENT_TOKENS)[number];
};
export type DeclaredCountAnswer = {
    kind: "declared";
    declarer_seat: number;
    declarer_points: number;
    opponents_points: number;
    ending: (typeof GAME_ENDING_TOKENS)[number];
    ended_by_seat: number | null;
};
export type DeclaringAnswer = {
    declarer_seat: number;
    stage: (typeof STAGE_TOKENS)[number];
    declaration: DeclarationAnswer | null;
    open_cards: CardAnswer[];
};
export type EmptyNoGamesAnswer = {
    reason: "empty";
    empty_seconds: number;
    unplayed_days: null;
    closed_by_name: null;
    standings: null;
    game_count: null;
};
export type EmptyWithGamesAnswer = {
    reason: "empty";
    empty_seconds: number;
    unplayed_days: null;
    closed_by_name: null;
    standings: StandingAnswer[];
    game_count: number;
};
export type GameSheetAnswer = {
    number: number;
    seat_names: (string | null)[];
    count: DeclaredCountAnswer | RamschCountAnswer;
    cards: SheetCardsAnswer | null;
};
export type GiveUpAnswer = {
    asking_seat: number;
    declined_seat: number | null;
};
export type GiveUpOptionsAnswer = {
    partner_agrees: boolean;
    any_time: boolean;
};
export type HandAnswer = {
    dealer_seat: number;
    own_cards: CardAnswer[];
    skat_count: number;
    auction: AuctionAnswer;
    declaring: DeclaringAnswer | null;
    playing: PlayingAnswer | null;
    ramsch: boolean;
    waiting_seat: number | null;
    pushing: PushingAnswer | null;
    pushes: number;
    push_factor: number;
    abort: number[] | null;
    abortable: boolean;
};
export type HandValueAnswer = {
    game: (typeof GAME_TOKENS)[number];
    value: number;
};
export type KontraAnswer = {
    said: SaidWordAnswer[];
    factor: number;
    my_word: (typeof WORD_TOKENS)[number] | null;
    my_word_answered: boolean;
    first_card_waits_on: number[];
    first_card_declined: number[];
};
export type KontraOptionsAnswer = {
    sayer: (typeof KONTRA_SAYER_TOKENS)[number];
    reach: (typeof KONTRA_REACH_TOKENS)[number];
    deadline: (typeof KONTRA_DEADLINE_TOKENS)[number];
};
export type KontraResultAnswer = {
    steps: KontraStepAnswer[];
};
export type KontraStepAnswer = {
    word: (typeof WORD_TOKENS)[number];
    factor: number;
};
export type LastTrickAnswer = {
    cards: CardAnswer[];
    leader_seat: number;
    taker_seat: number;
};
export type LobbyChairAnswer = {
    seat: number;
    occupant_name: string | null;
    occupant_kind: (typeof OCCUPANT_KIND_TOKENS)[number] | null;
    is_mine: boolean;
    ready: boolean;
    total: number | null;
    is_away: boolean;
    is_turn: boolean;
    hold_seconds_left: number | null;
    turn_state: TurnStateAnswer | null;
};
export type LobbyTableAnswer = {
    id: string;
    private: boolean;
    title_name: string | null;
    game_number: number | null;
    game_count: number | null;
    dealt: boolean;
    awaits_you: boolean;
    waits_on: (typeof WAITING_CASE_TOKENS)[number] | null;
    result_waits: boolean;
    series_over: boolean;
    ends_at: string | null;
    chairs: LobbyChairAnswer[];
};
export type MatadorsAnswer = {
    mit: boolean;
    count: number;
};
export type MineAnswer = {
    tables: LobbyTableAnswer[];
};
export type NextDealerAnswer = {
    next_dealer_seat: number | null;
};
export type NextSettingsAnswer = {
    game_count: number;
    options: OptionsAnswer;
    revision: number;
};
export type NudgeAnswer = {
    nudges: number;
    may_nudge: boolean;
    by_name: string | null;
};
export type OpenAnswer = {
    tables: OpenTableAnswer[];
};
export type OpenChairAnswer = {
    seat: number;
    occupant_name: string | null;
    occupant_kind: (typeof OCCUPANT_KIND_TOKENS)[number] | null;
    is_away: boolean;
    hold_seconds_left: number | null;
    turn_state: TurnStateAnswer | null;
};
export type OpenHandAnswer = {
    seat: number;
    cards: CardAnswer[];
};
export type OpenTableAnswer = {
    id: string;
    title_name: string | null;
    game_number: number | null;
    game_count: number | null;
    options: OptionsAnswer;
    watchers: number;
    free_chairs: number;
    dealt: boolean;
    waiting_seat: number | null;
    ends_at: string | null;
    chairs: OpenChairAnswer[];
};
export type OptionsAnswer = {
    show_running_points: boolean;
    kontra: KontraOptionsAnswer | null;
    bock: BockOptionsAnswer | null;
    ramsch: RamschOptionsAnswer | null;
    give_up: GiveUpOptionsAnswer;
};
export type PlayingAnswer = {
    turn_seat: number;
    current_trick: SeatedCardAnswer[];
    last_trick: LastTrickAnswer | null;
    taken: TakenAnswer[];
    legal_cards: CardAnswer[];
    running_points: SidesAnswer | null;
    give_up: GiveUpAnswer | null;
    shortening: ShorteningAnswer | null;
    shortening_refused_seat: number | null;
    open_play_seat: number | null;
    open_hands: OpenHandAnswer[];
    kontra: KontraAnswer | null;
};
export type PushingAnswer = {
    turn_seat: number;
    stage: (typeof STAGE_TOKENS)[number];
    moves: PushingMoveAnswer[];
    factor: number;
    put_back_cards: CardAnswer[];
};
export type PushingMoveAnswer = {
    seat: number;
    action: (typeof PUSH_ACTION_TOKENS)[number];
};
export type PushingOptionsAnswer = {
    rule: (typeof PUSHING_RULE_TOKENS)[number];
    grand_hand: (typeof GRAND_HAND_TOKENS)[number];
};
export type RamschCountAnswer = {
    kind: "ramsch";
    seat_points: number[];
    durchmarsch_seat: number | null;
};
export type RamschOptionsAnswer = {
    occasion: (typeof RAMSCH_OCCASION_TOKENS)[number];
    scoring: (typeof RAMSCH_SCORING_TOKENS)[number];
    jungfrau: (typeof JUNGFRAU_TOKENS)[number];
    durchmarsch: (typeof DURCHMARSCH_TOKENS)[number];
    pushing: PushingOptionsAnswer | null;
};
export type RamschResultAnswer = {
    kind: "ramsch";
    ordinal: number;
    seat_names: (string | null)[];
    seats: RamschSeatAnswer[];
    durchmarsch_seat: number | null;
    jungfrau: boolean;
    bock_factor: number;
    pushes: number;
    push_factor: number;
    divided_by_ten: boolean;
};
export type RamschSeatAnswer = {
    seat: number;
    points: number;
    score: number;
};
export type RamschSeriesEntryAnswer = {
    kind: "ramsch";
    number: number;
    seats: RamschSeriesSeatAnswer[];
    durchmarsch: boolean;
    jungfrau: boolean;
    bock_factor: number;
    pushes: number;
    push_factor: number;
};
export type RamschSeriesSeatAnswer = {
    name: string | null;
    kind: (typeof OCCUPANT_KIND_TOKENS)[number] | null;
    score: number;
};
export type ReactionAnswer = {
    number: number;
    reaction: (typeof REACTION_TOKENS)[number];
    by_seat: number | null;
    by_name: string | null;
};
export type RefusalAnswer = {
    reason: CommandRefusal | (typeof NUDGE_REFUSAL_TOKENS)[number] | (typeof REACTION_REFUSAL_TOKENS)[number];
    holder_name: string | null;
};
export type ResultAnswer = {
    kind: "declared";
    ordinal: number;
    seat_names: (string | null)[];
    declarer_seat: number;
    game: (typeof GAME_TOKENS)[number];
    hand: boolean;
    ouvert: boolean;
    announcement: (typeof ANNOUNCEMENT_TOKENS)[number];
    schneider: boolean;
    schwarz: boolean;
    matadors: MatadorsAnswer | null;
    base_value: number | null;
    levels: (typeof LEVEL_TOKENS)[number][];
    multiplier: number | null;
    list_bonus: number;
    announcement_missed: boolean;
    won: boolean;
    doubled: boolean;
    overbid: boolean;
    bid: number;
    game_value: number;
    settled_value: number;
    score: number;
    declarer_points: number;
    opponents_points: number;
    gains: SeatGainAnswer[];
    kontra: KontraResultAnswer | null;
    bock_factor: number;
    ending: (typeof GAME_ENDING_TOKENS)[number];
    ended_by_seat: number | null;
};
export type RuleSetAnswer = {
    id: string;
    name: string;
    options: OptionsAnswer;
};
export type RuleSetRefusalAnswer = {
    reason: (typeof RULE_SET_REFUSAL_TOKENS)[number];
};
export type RuleSetsAnswer = {
    sets: RuleSetAnswer[];
};
export type SaidWordAnswer = {
    seat: number;
    word: (typeof WORD_TOKENS)[number];
};
export type SeatGainAnswer = {
    seat: number;
    gain: number;
    won: boolean;
};
export type SeatedCardAnswer = {
    seat: number;
    card: CardAnswer;
};
export type SeriesAnswer = {
    number: number;
    game_number: number;
    game_count: number;
    over: boolean;
    standings: StandingAnswer[] | null;
    end_proposal: SeriesEndProposalAnswer | null;
    end_refused_seats: number[];
    new_series_answer_by: string | null;
    next_settings: NextSettingsAnswer | null;
};
export type SeriesEndProposalAnswer = {
    proposer_seat: number;
    agreed_seats: number[];
    answer_by: string;
};
export type SeriesEntryAnswer = {
    kind: "declared";
    number: number;
    declarer_name: string | null;
    declarer_seat: number;
    declarer_kind: (typeof OCCUPANT_KIND_TOKENS)[number] | null;
    game: (typeof GAME_TOKENS)[number];
    hand: boolean;
    ouvert: boolean;
    announcement: (typeof ANNOUNCEMENT_TOKENS)[number];
    levels: (typeof LEVEL_TOKENS)[number][];
    settled_value: number;
    score: number;
    declarer_points: number;
    kontra_word: (typeof WORD_TOKENS)[number] | null;
    bock_factor: number;
};
export type SeriesListAnswer = {
    entries: (SeriesEntryAnswer | RamschSeriesEntryAnswer)[];
};
export type SheetCardAnswer = {
    card: CardAnswer;
    state: (typeof CARD_STATE_TOKENS)[number];
};
export type SheetCardsAnswer = {
    hands: SheetHandAnswer[];
    skat: CardAnswer[];
    laid_skat: CardAnswer[];
    put_away: SeatedCardAnswer[];
    tricks: SheetTrickAnswer[];
    skat_takers: number[];
};
export type SheetHandAnswer = {
    seat: number;
    cards: SheetCardAnswer[];
};
export type SheetTrickAnswer = {
    number: number;
    cards: SeatedCardAnswer[];
    taker_seat: number | null;
    points: number | null;
};
export type ShorteningAnswer = {
    asking_seat: number;
    claim: (typeof ANNOUNCEMENT_TOKENS)[number];
    agreed_seat: number | null;
};
export type SidesAnswer = {
    declarer: number;
    opponents: number;
};
export type StandingAnswer = {
    display_name: string | null;
    seat: number;
    kind: (typeof OCCUPANT_KIND_TOKENS)[number] | null;
    total: number;
    won: number;
    lost: number;
    place: number;
};
export type TableAnswer = {
    id: string;
    version: number;
    chairs: ChairAnswer[];
    watchers: number;
    hand: HandAnswer | null;
    passed_in: NextDealerAnswer | null;
    aborted: NextDealerAnswer | null;
    result: ResultAnswer | RamschResultAnswer | null;
    series: SeriesAnswer | null;
    options: OptionsAnswer | null;
    style: (typeof TABLE_STYLE_TOKENS)[number] | null;
    bock: BockAnswer | null;
    ended:
        | EmptyNoGamesAnswer
        | EmptyWithGamesAnswer
        | UnplayedNoGamesAnswer
        | UnplayedWithGamesAnswer
        | ClosedNoGamesAnswer
        | ClosedWithGamesAnswer
        | null;
    reactions: ReactionAnswer[];
};
export type TakenAnswer = {
    seat: number;
    tricks: number;
};
export type TurnStateAnswer = {
    stopped: (typeof STOP_OUTCOME_TOKENS)[number] | null;
    thinking_seconds_left: number | null;
};
export type UnplayedNoGamesAnswer = {
    reason: "unplayed";
    empty_seconds: null;
    unplayed_days: number;
    closed_by_name: null;
    standings: null;
    game_count: null;
};
export type UnplayedWithGamesAnswer = {
    reason: "unplayed";
    empty_seconds: null;
    unplayed_days: number;
    closed_by_name: null;
    standings: StandingAnswer[];
    game_count: number;
};
