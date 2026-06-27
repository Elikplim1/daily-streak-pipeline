"""Pipeline configuration: env loading, signal thresholds, and constants.

All values come from .env or this file — never hardcoded elsewhere.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ["DATABASE_URL"]

# ── API-Football ──────────────────────────────────────────────────────────────
API_FOOTBALL_KEY: str = os.environ["API_FOOTBALL_KEY"]
API_FOOTBALL_BASE_URL: str = os.getenv(
    "API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io"
)
API_FOOTBALL_RATE_LIMIT: int = int(os.getenv("API_FOOTBALL_RATE_LIMIT", "300"))

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: str = os.environ["TELEGRAM_CHAT_ID"]
SHADOW_MODE: bool = os.getenv("SHADOW_MODE", "true").lower() == "true"

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

# Core 6 markets evaluated by the pipeline
CORE_MARKETS: list[str] = [
    "1x2",
    "btts",
    "goals_ou",
    "ht_1x2",
    "ht_btts",
    "cards_ou",
]

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
