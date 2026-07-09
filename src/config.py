"""Pipeline configuration: env loading, signal thresholds, and constants.

All values come from .env or this file — never hardcoded elsewhere.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ["DATABASE_URL"]

# ── API-Football ──────────────────────────────────────────────────────────────
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_FOOTBALL_BASE_URL: str = os.getenv(
    "API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io"
)
API_FOOTBALL_RATE_LIMIT: int = int(os.getenv("API_FOOTBALL_RATE_LIMIT", "300"))

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
SHADOW_MODE: bool = os.getenv("SHADOW_MODE", "true").lower() == "true"

# ── Spreadsheet export ────────────────────────────────────────────────────────
SPREADSHEET_ENABLED: bool = os.getenv("SPREADSHEET_ENABLED", "true").lower() == "true"

# ── Signal thresholds ─────────────────────────────────────────────────────────
# Three-lens streak model: venue_specific, overall, divergence_flag
# A fixture scores 0-5 across both teams × both lenses (venue + overall)
HIGH_SIGNAL_MIN_STREAK: int = 5     # 5/5: fires on all tiers
MODERATE_SIGNAL_MIN_STREAK: int = 4  # 4/5: fires on Full + Semi tiers
TRACKING_MIN_STREAK: int = 3         # 3/5: tracked but not broadcast

# Alignment engine thresholds (venue_confirmed model defaults)
ALIGNMENT_STRONG_CONFLUENCE_MIN: float = 1.5
ALIGNMENT_MILD_MIN: float = 0.5

# Sample gate: minimum completed fixtures before streaks are scored
MIN_FIXTURES_FULL: int = 10
MIN_FIXTURES_SEMI: int = 7
MIN_FIXTURES_MINI: int = 5

# Streak window: number of historical matches evaluated per team × lens
STREAK_WINDOW: int = 5

# Signal tier thresholds (streak count out of STREAK_WINDOW)
HIGH_SIGNAL_MIN: int = 5
MODERATE_SIGNAL_MIN: int = 4

# Per-market threshold overrides for markets where NON_OCCURRENCE is the
# baseline (>70% natural rate) — the default HIGH_SIGNAL_MIN/MODERATE_SIGNAL_MIN
# (5/4) are too easy to hit by chance for these, so they need a higher bar.
#
# NOTE: streak_length is capped at STREAK_WINDOW (5) — scan_fixture() only
# evaluates the last 5 matches per team × lens, so no threshold here can
# exceed 5. The values below are clamped to that ceiling: "high" is 5 (the
# max achievable, same ceiling as the default) and "moderate" is likewise
# raised to 5, since anything strictly between the default's 4 and the
# ceiling of 5 doesn't exist as an integer. In practice this means these
# markets only register as a signal (MODERATE or HIGH) on a perfect 5/5
# streak — a 4/5 streak, which is enough for MODERATE on every other
# market, stays at TRACKING for these.
MARKET_THRESHOLD_OVERRIDES: dict[str, dict[str, int]] = {
    "no_goal_5min": {"high": 5, "moderate": 5},
    "no_goal_10min": {"high": 5, "moderate": 5},
    "no_home_3plus": {"high": 5, "moderate": 5},
    "no_away_3plus": {"high": 5, "moderate": 5},
    "no_win_nil_home": {"high": 5, "moderate": 5},
    "no_win_nil_away": {"high": 5, "moderate": 5},
    "no_home_2plus": {"high": 5, "moderate": 5},
    "no_away_2plus": {"high": 5, "moderate": 5},
}

# Markets that are SUPPORTING EVIDENCE only: still calculated, still shown
# in the spreadsheet (labeled "SUPPORTING" there), but never generate a
# HIGH_SIGNAL or MODERATE_SIGNAL alert on their own — always TRACKING,
# regardless of streak length or alignment.
SUPPORTING_EVIDENCE_ONLY: list[str] = [
    "no_goal_5min",
    "no_goal_10min",
    "no_home_3plus",
    "no_away_3plus",
    "no_win_nil_home",
    "no_win_nil_away",
    "no_home_2plus",
    "no_away_2plus",
]

# All 59 markets scanned by the pipeline (11 original + 28 in Session 5A + 20 in Session 5B)
SCAN_MARKETS: list[str] = [
    # === EXISTING 11 ===
    "ft_win", "ht_win",
    "dc_1x_ft", "dc_x2_ft", "dc_1x_ht", "dc_x2_ht",
    "gg_ft", "over_2_5", "under_2_5", "under_3_5", "hsh_2h",
    # === NEW SCORE-BASED (Session 5A) ===
    "over_1_5", "under_1_5", "over_4_5",
    "btts_over25",
    "ht_00",
    "no_win_nil_home", "no_win_nil_away",
    "no_home_2plus", "no_away_2plus",
    "no_home_3plus", "no_away_3plus",
    "no_both_halves_over05", "both_halves_under15",
    "odd_total_ft", "hsh_1h",
    "htft_home_home", "htft_draw_home",
    # === MULTISCORE GROUPS (Session 5A) ===
    "ms_home_nil_low", "ms_away_nil_low",
    "ms_home_blowout", "ms_away_blowout",
    "ms_home_comfort", "ms_away_comfort",
    "ms_high_home", "ms_high_away",
    "ms_draw",
    # === EVENT-BASED (Session 5A) ===
    "no_goal_5min", "no_goal_10min",
    # === CORNERS — TOTAL (Session 5B) ===
    "over_8_5_corners", "under_8_5_corners",
    "over_9_5_corners", "under_9_5_corners",
    "over_10_5_corners", "under_10_5_corners",
    "over_11_5_corners", "under_11_5_corners",
    # === CORNERS — TEAM (Session 5B) ===
    "over_3_5_team_corners", "under_3_5_team_corners",
    "over_4_5_team_corners", "under_4_5_team_corners",
    "over_5_5_team_corners", "under_5_5_team_corners",
    # === CARDS — TOTAL (Session 5B) ===
    "over_2_5_cards", "under_2_5_cards",
    "over_3_5_cards", "under_3_5_cards",
    # === CARDS — TEAM (Session 5B) ===
    "over_1_5_team_cards", "under_1_5_team_cards",
]

# Legacy alias kept for backwards compatibility
CORE_MARKETS: list[str] = SCAN_MARKETS

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
