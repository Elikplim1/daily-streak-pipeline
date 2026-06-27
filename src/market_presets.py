"""
Market preset definitions for the daily-streak-pipeline.

Each preset defines:
- key: unique identifier
- name: human-readable name
- match_type: alignment rule (COMPLEMENTARY, SAME_PATTERN, COMBINED, FLEXIBLE_OR)
- streak_type: classification (OCCURRENCE, NON_OCCURRENCE, DIRECTIONAL, INTERACTION)
- evaluate_home(fixture_row): returns True if the market condition is met for the HOME team
- evaluate_away(fixture_row): returns True if the market condition is met for the AWAY team

fixture_row is a dict with keys matching the Supabase fixtures table columns
(confirmed via Step 0 schema discovery):
  ft_home, ft_away, ht_home, ht_away, sh_home (GENERATED), sh_away (GENERATED),
  home_team_id, away_team_id
"""
from dataclasses import dataclass
from typing import Callable, Dict, Optional


class MatchType:
    """How alignment between two teams' streaks is evaluated."""
    COMPLEMENTARY = "COMPLEMENTARY"
    SAME_PATTERN = "SAME_PATTERN"
    COMBINED = "COMBINED"
    FLEXIBLE_OR = "FLEXIBLE_OR"


class StreakType:
    """Classification of what the streak measures."""
    OCCURRENCE = "OCCURRENCE"
    NON_OCCURRENCE = "NON_OCCURRENCE"
    DIRECTIONAL = "DIRECTIONAL"
    INTERACTION = "INTERACTION"


@dataclass
class MarketPreset:
    """Definition of a single market for streak scanning."""
    key: str
    name: str
    match_type: str
    streak_type: str
    evaluate_home: Callable[[dict], Optional[bool]]
    evaluate_away: Callable[[dict], Optional[bool]]
    description: str = ""


# === EVALUATION HELPERS ===

def _scores_available(f: dict, level: str = 'ft') -> bool:
    """Check if the required score columns are non-None."""
    if level == 'ft':
        return f.get('ft_home') is not None and f.get('ft_away') is not None
    elif level == 'ht':
        return f.get('ht_home') is not None and f.get('ht_away') is not None
    elif level == 'sh':
        return f.get('sh_home') is not None and f.get('sh_away') is not None
    return False


def _total_goals(f: dict) -> Optional[int]:
    """Total full-time goals, or None if scores are unavailable."""
    if not _scores_available(f, 'ft'):
        return None
    return f['ft_home'] + f['ft_away']


# === FULL-TIME WIN ===

def eval_ft_win_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] > f['ft_away']

def eval_ft_win_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] > f['ft_home']


# === HALF-TIME WIN ===

def eval_ht_win_home(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht'): return None
    return f['ht_home'] > f['ht_away']

def eval_ht_win_away(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht'): return None
    return f['ht_away'] > f['ht_home']


# === DOUBLE CHANCE 1X FT (Home Win or Draw) ===

def eval_dc_1x_ft_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] >= f['ft_away']

def eval_dc_1x_ft_away(f: dict) -> Optional[bool]:
    """Away team LOST (complement)."""
    if not _scores_available(f): return None
    return f['ft_away'] < f['ft_home']


# === DOUBLE CHANCE X2 FT (Away Win or Draw) ===

def eval_dc_x2_ft_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] <= f['ft_away']

def eval_dc_x2_ft_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] >= f['ft_home']


# === DOUBLE CHANCE 1X HT ===

def eval_dc_1x_ht_home(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht'): return None
    return f['ht_home'] >= f['ht_away']

def eval_dc_1x_ht_away(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht'): return None
    return f['ht_away'] < f['ht_home']


# === DOUBLE CHANCE X2 HT ===

def eval_dc_x2_ht_home(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht'): return None
    return f['ht_home'] <= f['ht_away']

def eval_dc_x2_ht_away(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht'): return None
    return f['ht_away'] >= f['ht_home']


# === BTTS (Both Teams to Score) ===

def eval_btts_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] > 0 and f['ft_away'] > 0

def eval_btts_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] > 0 and f['ft_away'] > 0


# === OVER 2.5 GOALS ===

def eval_over25_home(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total > 2

def eval_over25_away(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total > 2


# === UNDER 2.5 GOALS ===

def eval_under25_home(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total < 3

def eval_under25_away(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total < 3


# === UNDER 3.5 GOALS ===

def eval_under35_home(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total < 4

def eval_under35_away(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total < 4


# === HIGHEST SCORING HALF: 2ND HALF ===

def eval_hsh_2h_home(f: dict) -> Optional[bool]:
    """2nd half had MORE goals than 1st half."""
    if not _scores_available(f, 'ht') or not _scores_available(f, 'ft'):
        return None
    first_half = f['ht_home'] + f['ht_away']
    total = f['ft_home'] + f['ft_away']
    second_half = total - first_half
    return second_half > first_half

def eval_hsh_2h_away(f: dict) -> Optional[bool]:
    return eval_hsh_2h_home(f)


# === CORE MARKET REGISTRY ===

CORE_MARKETS: Dict[str, MarketPreset] = {
    "ft_win": MarketPreset(
        key="ft_win", name="Full-Time Win",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.DIRECTIONAL,
        evaluate_home=eval_ft_win_home, evaluate_away=eval_ft_win_away,
        description="Home team wins FT; away side checks for loss.",
    ),
    "ht_win": MarketPreset(
        key="ht_win", name="Half-Time Win",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.DIRECTIONAL,
        evaluate_home=eval_ht_win_home, evaluate_away=eval_ht_win_away,
        description="Home leads at HT; away side checks for trailing.",
    ),
    "dc_1x_ft": MarketPreset(
        key="dc_1x_ft", name="Double Chance 1X (FT)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_dc_1x_ft_home, evaluate_away=eval_dc_1x_ft_away,
        description="Home doesn't lose (1X FT); away checks for losing.",
    ),
    "dc_x2_ft": MarketPreset(
        key="dc_x2_ft", name="Double Chance X2 (FT)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_dc_x2_ft_home, evaluate_away=eval_dc_x2_ft_away,
        description="Home doesn't win (X2 FT); away checks for not losing.",
    ),
    "dc_1x_ht": MarketPreset(
        key="dc_1x_ht", name="Double Chance 1X (HT)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_dc_1x_ht_home, evaluate_away=eval_dc_1x_ht_away,
        description="Home doesn't lose at HT; away checks for trailing.",
    ),
    "dc_x2_ht": MarketPreset(
        key="dc_x2_ht", name="Double Chance X2 (HT)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_dc_x2_ht_home, evaluate_away=eval_dc_x2_ht_away,
        description="Home doesn't win at HT; away checks for not losing.",
    ),
    "gg_ft": MarketPreset(
        key="gg_ft", name="Both Teams to Score (BTTS)",
        match_type=MatchType.SAME_PATTERN, streak_type=StreakType.INTERACTION,
        evaluate_home=eval_btts_home, evaluate_away=eval_btts_away,
        description="Both teams scored. SAME_PATTERN: both sides check identical condition.",
    ),
    "over_2_5": MarketPreset(
        key="over_2_5", name="Over 2.5 Goals",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_over25_home, evaluate_away=eval_over25_away,
        description="3+ total goals. COMBINED: both teams' matches individually show this.",
    ),
    "under_2_5": MarketPreset(
        key="under_2_5", name="Under 2.5 Goals",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_under25_home, evaluate_away=eval_under25_away,
        description="Fewer than 3 total goals.",
    ),
    "under_3_5": MarketPreset(
        key="under_3_5", name="Under 3.5 Goals",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_under35_home, evaluate_away=eval_under35_away,
        description="Fewer than 4 total goals.",
    ),
    "hsh_2h": MarketPreset(
        key="hsh_2h", name="Highest Scoring Half (2nd Half)",
        match_type=MatchType.FLEXIBLE_OR, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_hsh_2h_home, evaluate_away=eval_hsh_2h_away,
        description="2nd half has more goals than 1st. FLEXIBLE_OR: either team shows it.",
    ),
}


def get_market(key: str) -> Optional[MarketPreset]:
    """Retrieve a market preset by key."""
    return CORE_MARKETS.get(key)


def get_all_markets() -> Dict[str, MarketPreset]:
    """Return all registered market presets."""
    return CORE_MARKETS.copy()
