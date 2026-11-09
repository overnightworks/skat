// Generated from the Python path and token owners by scripts/generate_wire.py. Do not edit.

export const AUTH_START_PATH = "/auth/start";
export const RETURN_PATH_QUERY_NAME = "next";
export const SIGNED_IN_AGAIN_QUERY_NAME = "signedInAgain";
export const LOGOUT_PATH = "/logout";
export const ACCOUNT_PATH = "/api/account";
export const ACCOUNT_CONSOLE_PATH = "/account";
export const TABLES_PATH = "/api/tables";
export const TABLE_PAGE_PREFIX = "/t/";
export const TABLE_EVENTS_SUFFIX = "/events";
export const TABLE_SIT_SUFFIX = "/sit";
export const TABLE_STAND_SUFFIX = "/stand";
export const TABLE_DECLARING_TAKE_SUFFIX = "/declaring/take";
export const TABLE_DECLARING_PUT_BACK_SUFFIX = "/declaring/put-back";
export const TABLE_DECLARING_DECLARE_SUFFIX = "/declaring/declare";
export const TABLE_AUCTION_BID_SUFFIX = "/auction/bid";
export const TABLE_AUCTION_HOLD_SUFFIX = "/auction/hold";
export const TABLE_AUCTION_PASS_SUFFIX = "/auction/pass";
export const TABLE_AUCTION_PLAY_SUFFIX = "/auction/play";
export const TABLE_CARD_SUFFIX = "/card";
export const TABLE_READY_SUFFIX = "/ready";
export const SUIT_TOKENS = ["kreuz", "pik", "herz", "karo"] as const;
export const RANK_TOKENS = ["seven", "eight", "nine", "ten", "jack", "queen", "king", "ace"] as const;
export const POSITION_TOKENS = ["forehand", "middlehand", "rearhand"] as const;
export const GAME_TOKENS = ["karo", "herz", "pik", "kreuz", "grand", "null"] as const;
export const ANNOUNCEMENT_TOKENS = ["none", "schneider", "schwarz"] as const;
export const STAGE_TOKENS = ["choosing", "discarding", "picked", "declared"] as const;
export const AWAITING_TOKENS = ["bid", "answer", "play"] as const;
export const AUCTION_ACTION_TOKENS = ["bid", "hold", "pass", "play"] as const;
export const VALID_BIDS = [
    18, 20, 22, 23, 24, 27, 30, 33, 35, 36, 40, 44, 45, 46, 48, 50, 54, 55, 59, 60, 63, 66, 70, 72, 77, 80, 81, 84, 88,
    90, 96, 99, 100, 108, 110, 117, 120, 121, 126, 130, 132, 135, 140, 143, 144, 150, 153, 154, 156, 160, 162, 165, 168,
    170, 176, 180, 187, 192, 198, 204, 216, 240, 264,
] as const;
export const ALL_POINTS = 120;
