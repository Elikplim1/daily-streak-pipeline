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

# All 39 markets scanned by the pipeline (11 original + 28 added in Session 5A)
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
]

# Legacy alias kept for backwards compatibility
CORE_MARKETS: list[str] = SCAN_MARKETS

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
