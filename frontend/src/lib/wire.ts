// Generated from the Python path and token owners by scripts/generate_wire.py. Do not edit.

export const AUTH_START_PATH = "/auth/start";
export const RETURN_PATH_QUERY_NAME = "next";
export const SIGNED_IN_AGAIN_QUERY_NAME = "signedInAgain";
export const NO_ACCESS_PATH = "/no-access";
export const MODE_QUERY_NAME = "mode";
export const CALL_MODE = "call";
export const LOGOUT_PATH = "/logout";
export const ACCOUNT_PATH = "/api/account";
export const VERSION_FILE_PATH = "/_app/version.json";
export const CALL_ORIGIN_PATH = "/api/call-origin";
export const ACCOUNT_CONSOLE_PATH = "/account";
export const TABLES_PATH = "/api/tables";
export const LOBBY_EVENTS_PATH = "/api/lobby/events";
export const TABLE_PAGE_PREFIX = "/t/";
export const TABLE_ID_PATTERN = "[0-9a-f]{32}";
export const TABLE_EVENTS_SUFFIX = "/events";
export const TABLE_SIT_SUFFIX = "/sit";
export const TABLE_STAND_SUFFIX = "/stand";
export const TABLE_CLOSE_SUFFIX = "/close";
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
export const TABLE_AUCTION_PLAY_SUFFIX = "/auction/play";
export const TABLE_CARD_SUFFIX = "/card";
export const TABLE_GIVE_UP_SUFFIX = "/give-up";
export const TABLE_GIVE_UP_AGREE_SUFFIX = "/give-up/agree";
export const TABLE_GIVE_UP_DECLINE_SUFFIX = "/give-up/decline";
export const TABLE_LIST_SUFFIX = "/list";
export const TABLE_KONTRA_SUFFIX = "/kontra";
export const TABLE_NO_WORD_SUFFIX = "/kontra/no-word";
export const TABLE_READY_SUFFIX = "/ready";
export const TABLE_AGENTS_SUFFIX = "/agents";
export const TABLE_AGENT_CALL_SUFFIX = "/call";
export const TABLE_AGENT_SEND_AWAY_SUFFIX = "/send-away";
export const TABLE_ABORT_AGREE_SUFFIX = "/abort/agree";
export const TABLE_ABORT_REFUSE_SUFFIX = "/abort/refuse";
export const SUIT_TOKENS = ["kreuz", "pik", "herz", "karo"] as const;
export const RANK_TOKENS = ["seven", "eight", "nine", "ten", "jack", "queen", "king", "ace"] as const;
export const POSITION_TOKENS = ["forehand", "middlehand", "rearhand"] as const;
export const GAME_TOKENS = ["karo", "herz", "pik", "kreuz", "grand", "null"] as const;
export const ANNOUNCEMENT_TOKENS = ["none", "schneider", "schwarz"] as const;
export const STAGE_TOKENS = ["choosing", "discarding", "picked", "declared"] as const;
export const AWAITING_TOKENS = ["bid", "answer", "play"] as const;
export const AUCTION_ACTION_TOKENS = ["bid", "hold", "pass", "play"] as const;
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
export const RAMSCH_SCORING_TOKENS = ["points", "points-by-ten", "skat-to-loser"] as const;
export const JUNGFRAU_TOKENS = ["doubles-loser", "off"] as const;
export const DURCHMARSCH_TOKENS = ["wins-120", "wins-120-flat", "off"] as const;
export const PUSHING_RULE_TOKENS = ["jacks-stay", "jacks-may-go", "no-doubling"] as const;
export const GRAND_HAND_TOKENS = ["allowed", "off"] as const;
export const WAITING_CASE_TOKENS = ["turn", "give_up", "kontra", "end_proposal", "result", "series_end"] as const;
export const GAME_ENDING_TOKENS = ["played-out", "given-up", "thrown-down"] as const;
export const WORD_TOKENS = ["kontra", "re", "supra", "hirsch"] as const;
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
