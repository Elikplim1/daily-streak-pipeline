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
from functools import partial
from typing import Callable, Dict, Optional


class MatchType:
    """How alignment between two teams' streaks is evaluated."""
    COMPLEMENTARY = "COMPLEMENTARY"
    SAME_PATTERN = "SAME_PATTERN"
    COMBINED = "COMBINED"
    FLEXIBLE_OR = "FLEXIBLE_OR"
    CROSS_COMPLEMENTARY = "CROSS_COMPLEMENTARY"  # Offensive vs defensive cross-check


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
    # Cross-complementary fields (optional — only for CROSS_COMPLEMENTARY markets)
    evaluate_cross_defensive_home: Optional[Callable[[dict], Optional[bool]]] = None
    evaluate_cross_offensive_away: Optional[Callable[[dict], Optional[bool]]] = None
    # For stats-based markets (queried from fixture_stats_football, not fixtures)
    stats_based: bool = False
    stats_column: str = ""  # Column name in fixture_stats_football
    stats_threshold: float = 0
    stats_over: bool = True  # True = over, False = under


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


# === SESSION 5A: NEW GOAL LINE MARKETS ===

# --- Over 1.5 Goals ---
def eval_over15_home(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total > 1

def eval_over15_away(f: dict) -> Optional[bool]:
    return eval_over15_home(f)

# --- Under 1.5 Goals ---
def eval_under15_home(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total < 2

def eval_under15_away(f: dict) -> Optional[bool]:
    return eval_under15_home(f)

# --- Over 4.5 Goals ---
def eval_over45_home(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total > 4

def eval_over45_away(f: dict) -> Optional[bool]:
    return eval_over45_home(f)

# --- BTTS + Over 2.5 Combo ---
def eval_btts_over25_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    both_scored = f['ft_home'] > 0 and f['ft_away'] > 0
    over25 = (f['ft_home'] + f['ft_away']) > 2
    return both_scored and over25

def eval_btts_over25_away(f: dict) -> Optional[bool]:
    return eval_btts_over25_home(f)


# === SESSION 5A: NON_OCCURRENCE MARKETS (tracking when things DON'T happen) ===

# --- No Win to Nil: Home team did NOT (win AND keep clean sheet) ---
def eval_no_win_nil_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    win_to_nil = f['ft_home'] > f['ft_away'] and f['ft_away'] == 0
    return not win_to_nil  # True when it DID NOT happen

def eval_no_win_nil_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    win_to_nil = f['ft_away'] > f['ft_home'] and f['ft_home'] == 0
    return not win_to_nil

# --- Home NOT scoring 2+ (scored 0 or 1) ---
def eval_no_home_2plus_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] < 2

def eval_no_home_2plus_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] < 2  # Still evaluating the HOME team's goals

# --- Away NOT scoring 2+ ---
def eval_no_away_2plus_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] < 2

def eval_no_away_2plus_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] < 2

# --- Home NOT scoring 3+ ---
def eval_no_home_3plus_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] < 3

def eval_no_home_3plus_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] < 3

# --- Away NOT scoring 3+ ---
def eval_no_away_3plus_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] < 3

def eval_no_away_3plus_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] < 3


# === SESSION 5A: HALF STRUCTURE MARKETS ===

# --- NOT both halves over 0.5 goals (at least one half was goalless) ---
def eval_no_both_halves_over05_home(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht') or not _scores_available(f, 'ft'):
        return None
    first_half_goals = f['ht_home'] + f['ht_away']
    total = f['ft_home'] + f['ft_away']
    second_half_goals = total - first_half_goals
    both_halves_scored = first_half_goals > 0 and second_half_goals > 0
    return not both_halves_scored  # True when at least one half was goalless

def eval_no_both_halves_over05_away(f: dict) -> Optional[bool]:
    return eval_no_both_halves_over05_home(f)

# --- Both halves under 1.5 goals (each half had 0 or 1 goal) ---
def eval_both_halves_under15_home(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht') or not _scores_available(f, 'ft'):
        return None
    first_half_goals = f['ht_home'] + f['ht_away']
    total = f['ft_home'] + f['ft_away']
    second_half_goals = total - first_half_goals
    return first_half_goals < 2 and second_half_goals < 2

def eval_both_halves_under15_away(f: dict) -> Optional[bool]:
    return eval_both_halves_under15_home(f)

# --- Odd total goals FT ---
def eval_odd_total_home(f: dict) -> Optional[bool]:
    total = _total_goals(f)
    if total is None: return None
    return total % 2 == 1

def eval_odd_total_away(f: dict) -> Optional[bool]:
    return eval_odd_total_home(f)

# --- HSH 1st Half (first half had more goals than second) ---
def eval_hsh_1h_home(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht') or not _scores_available(f, 'ft'):
        return None
    first_half_goals = f['ht_home'] + f['ht_away']
    total = f['ft_home'] + f['ft_away']
    second_half_goals = total - first_half_goals
    return first_half_goals > second_half_goals

def eval_hsh_1h_away(f: dict) -> Optional[bool]:
    return eval_hsh_1h_home(f)

# --- HT 0-0 Scoreline ---
def eval_ht_00_home(f: dict) -> Optional[bool]:
    if not _scores_available(f, 'ht'): return None
    return f['ht_home'] == 0 and f['ht_away'] == 0

def eval_ht_00_away(f: dict) -> Optional[bool]:
    return eval_ht_00_home(f)

# --- HT/FT Home-Home (home leads HT and wins FT) ---
def eval_htft_hh_home(f: dict) -> Optional[bool]:
    if not _scores_available(f) or not _scores_available(f, 'ht'):
        return None
    ht_lead = f['ht_home'] > f['ht_away']
    ft_win = f['ft_home'] > f['ft_away']
    return ht_lead and ft_win

def eval_htft_hh_away(f: dict) -> Optional[bool]:
    """Away perspective: away leads HT and wins FT"""
    if not _scores_available(f) or not _scores_available(f, 'ht'):
        return None
    ht_lead = f['ht_away'] > f['ht_home']
    ft_win = f['ft_away'] > f['ft_home']
    return ht_lead and ft_win

# --- HT Draw → FT Home Win ---
def eval_htft_dh_home(f: dict) -> Optional[bool]:
    if not _scores_available(f) or not _scores_available(f, 'ht'):
        return None
    ht_draw = f['ht_home'] == f['ht_away']
    ft_home_win = f['ft_home'] > f['ft_away']
    return ht_draw and ft_home_win

def eval_htft_dh_away(f: dict) -> Optional[bool]:
    """Away perspective: HT draw, away wins FT"""
    if not _scores_available(f) or not _scores_available(f, 'ht'):
        return None
    ht_draw = f['ht_home'] == f['ht_away']
    ft_away_win = f['ft_away'] > f['ft_home']
    return ht_draw and ft_away_win


# === SESSION 5A: MULTISCORE GROUP MARKETS ===

# --- Multiscore: Home Win to Nil Low (1-0, 2-0, 3-0) ---
def eval_ms_home_nil_low_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(1,0), (2,0), (3,0)]

def eval_ms_home_nil_low_away(f: dict) -> Optional[bool]:
    return eval_ms_home_nil_low_home(f)

# --- Away Win to Nil Low (0-1, 0-2, 0-3) ---
def eval_ms_away_nil_low_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(0,1), (0,2), (0,3)]

def eval_ms_away_nil_low_away(f: dict) -> Optional[bool]:
    return eval_ms_away_nil_low_home(f)

# --- Home Blowout (4-0, 5-0, 6-0) ---
def eval_ms_home_blowout_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(4,0), (5,0), (6,0)]

def eval_ms_home_blowout_away(f: dict) -> Optional[bool]:
    return eval_ms_home_blowout_home(f)

# --- Away Blowout (0-4, 0-5, 0-6) ---
def eval_ms_away_blowout_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(0,4), (0,5), (0,6)]

def eval_ms_away_blowout_away(f: dict) -> Optional[bool]:
    return eval_ms_away_blowout_home(f)

# --- Home Comfortable (2-1, 3-1, 4-1) ---
def eval_ms_home_comfort_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(2,1), (3,1), (4,1)]

def eval_ms_home_comfort_away(f: dict) -> Optional[bool]:
    return eval_ms_home_comfort_home(f)

# --- Away Comfortable (1-2, 1-3, 1-4) ---
def eval_ms_away_comfort_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(1,2), (1,3), (1,4)]

def eval_ms_away_comfort_away(f: dict) -> Optional[bool]:
    return eval_ms_away_comfort_home(f)

# --- High-Score Home Win (3-2, 4-2, 4-3, 5-1) ---
def eval_ms_high_home_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(3,2), (4,2), (4,3), (5,1)]

def eval_ms_high_home_away(f: dict) -> Optional[bool]:
    return eval_ms_high_home_home(f)

# --- High-Score Away Win (2-3, 2-4, 3-4, 1-5) ---
def eval_ms_high_away_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return (f['ft_home'], f['ft_away']) in [(2,3), (2,4), (3,4), (1,5)]

def eval_ms_high_away_away(f: dict) -> Optional[bool]:
    return eval_ms_high_away_home(f)

# --- Draw (any draw scoreline) ---
def eval_ms_draw_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] == f['ft_away']

def eval_ms_draw_away(f: dict) -> Optional[bool]:
    return eval_ms_draw_home(f)


# === SESSION 5B: CROSS-COMPLEMENTARY EVALUATION FUNCTIONS ===
# These evaluate the DEFENSIVE side (goals conceded) or OFFENSIVE side (goals scored)
# separately, unlike the regular evaluators which check total goals.
#
# For a fixture where TeamA is the team being evaluated:
# - If TeamA was HOME: ft_home = their goals, ft_away = goals they conceded
# - If TeamA was AWAY: ft_away = their goals, ft_home = goals they conceded

def eval_cross_concedes_under_2_home(f: dict) -> Optional[bool]:
    """Home team conceded fewer than 2 goals (defensive strength)."""
    if not _scores_available(f): return None
    return f['ft_away'] < 2  # Goals scored BY opponent = goals conceded BY home team

def eval_cross_concedes_under_2_away(f: dict) -> Optional[bool]:
    """Away team conceded fewer than 2 goals."""
    if not _scores_available(f): return None
    return f['ft_home'] < 2  # Goals scored BY opponent = goals conceded BY away team

def eval_cross_scores_under_2_home(f: dict) -> Optional[bool]:
    """Home team scored fewer than 2 goals (offensive weakness)."""
    if not _scores_available(f): return None
    return f['ft_home'] < 2

def eval_cross_scores_under_2_away(f: dict) -> Optional[bool]:
    """Away team scored fewer than 2 goals."""
    if not _scores_available(f): return None
    return f['ft_away'] < 2

def eval_cross_concedes_under_3_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] < 3

def eval_cross_concedes_under_3_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] < 3

def eval_cross_scores_under_3_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] < 3

def eval_cross_scores_under_3_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] < 3

# Over versions: check if teams SCORE/CONCEDE 2+
def eval_cross_concedes_over_2_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] >= 2

def eval_cross_scores_over_2_home(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] >= 2

def eval_cross_concedes_over_2_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_home'] >= 2

def eval_cross_scores_over_2_away(f: dict) -> Optional[bool]:
    if not _scores_available(f): return None
    return f['ft_away'] >= 2


# === SESSION 5B: STATS-BASED MARKET EVALUATORS (corners, yellow cards) ===
# These read 'home_stat'/'away_stat' keys populated by
# streak_scanner.get_team_recent_stats() — NOT ft_home/ft_away.
# Bound to a specific line via functools.partial(threshold=...) at registration.
#
# NOTE: for "Under X.5" the comparison is `< threshold` directly (threshold
# is already the .5 line, e.g. 8.5) — NOT `< threshold + 1`, which would
# incorrectly shift the line up by one whole goal/corner/card and let e.g.
# a total of 9 pass an "Under 8.5" check.

def eval_over_corners_total(f: dict, threshold: float) -> Optional[bool]:
    """Total match corners > threshold."""
    h = f.get('home_stat')
    a = f.get('away_stat')
    if h is None or a is None: return None
    return (h + a) > threshold

def eval_under_corners_total(f: dict, threshold: float) -> Optional[bool]:
    """Total match corners < threshold (e.g. Under 8.5 means total <= 8)."""
    h = f.get('home_stat')
    a = f.get('away_stat')
    if h is None or a is None: return None
    return (h + a) < threshold

def eval_over_team_stat_home(f: dict, threshold: float) -> Optional[bool]:
    """Home team's stat > threshold."""
    h = f.get('home_stat')
    if h is None: return None
    return h > threshold

def eval_over_team_stat_away(f: dict, threshold: float) -> Optional[bool]:
    a = f.get('away_stat')
    if a is None: return None
    return a > threshold

def eval_under_team_stat_home(f: dict, threshold: float) -> Optional[bool]:
    h = f.get('home_stat')
    if h is None: return None
    return h < threshold

def eval_under_team_stat_away(f: dict, threshold: float) -> Optional[bool]:
    a = f.get('away_stat')
    if a is None: return None
    return a < threshold


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
        match_type=MatchType.CROSS_COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_over25_home, evaluate_away=eval_over25_away,
        evaluate_cross_defensive_home=eval_cross_concedes_over_2_home,
        evaluate_cross_offensive_away=eval_cross_scores_over_2_away,
        description="3+ total goals. Cross-validated: home defense vs away offense.",
    ),
    "under_2_5": MarketPreset(
        key="under_2_5", name="Under 2.5 Goals",
        match_type=MatchType.CROSS_COMPLEMENTARY, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_under25_home, evaluate_away=eval_under25_away,
        evaluate_cross_defensive_home=eval_cross_concedes_under_3_home,
        evaluate_cross_offensive_away=eval_cross_scores_under_3_away,
        description="Fewer than 3 total goals. Cross-validated: home defense vs away offense.",
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
    # === SESSION 5A ADDITIONS (28 new markets) ===
    "over_1_5": MarketPreset(
        key="over_1_5", name="Over 1.5 Goals",
        match_type=MatchType.CROSS_COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_over15_home, evaluate_away=eval_over15_away,
        evaluate_cross_defensive_home=eval_cross_concedes_over_2_home,
        evaluate_cross_offensive_away=eval_cross_scores_over_2_away,
    ),
    "under_1_5": MarketPreset(
        key="under_1_5", name="Under 1.5 Goals",
        match_type=MatchType.CROSS_COMPLEMENTARY, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_under15_home, evaluate_away=eval_under15_away,
        evaluate_cross_defensive_home=eval_cross_concedes_under_2_home,
        evaluate_cross_offensive_away=eval_cross_scores_under_2_away,
    ),
    "over_4_5": MarketPreset(
        key="over_4_5", name="Over 4.5 Goals",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_over45_home, evaluate_away=eval_over45_away,
    ),
    "btts_over25": MarketPreset(
        key="btts_over25", name="BTTS + Over 2.5",
        match_type=MatchType.SAME_PATTERN, streak_type=StreakType.INTERACTION,
        evaluate_home=eval_btts_over25_home, evaluate_away=eval_btts_over25_away,
    ),
    "ht_00": MarketPreset(
        key="ht_00", name="HT 0-0 Scoreline",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ht_00_home, evaluate_away=eval_ht_00_away,
    ),
    "no_win_nil_home": MarketPreset(
        key="no_win_nil_home", name="No Win to Nil (Home)",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_no_win_nil_home, evaluate_away=eval_no_win_nil_away,
    ),
    "no_win_nil_away": MarketPreset(
        key="no_win_nil_away", name="No Win to Nil (Away)",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_no_win_nil_away, evaluate_away=eval_no_win_nil_home,
    ),
    "no_home_2plus": MarketPreset(
        key="no_home_2plus", name="Home NOT Scoring 2+",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_no_home_2plus_home, evaluate_away=eval_no_home_2plus_away,
    ),
    "no_away_2plus": MarketPreset(
        key="no_away_2plus", name="Away NOT Scoring 2+",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_no_away_2plus_home, evaluate_away=eval_no_away_2plus_away,
    ),
    "no_home_3plus": MarketPreset(
        key="no_home_3plus", name="Home NOT Scoring 3+",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_no_home_3plus_home, evaluate_away=eval_no_home_3plus_away,
    ),
    "no_away_3plus": MarketPreset(
        key="no_away_3plus", name="Away NOT Scoring 3+",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_no_away_3plus_home, evaluate_away=eval_no_away_3plus_away,
    ),
    "no_both_halves_over05": MarketPreset(
        key="no_both_halves_over05", name="NOT Goals in Both Halves",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=eval_no_both_halves_over05_home, evaluate_away=eval_no_both_halves_over05_away,
    ),
    "both_halves_under15": MarketPreset(
        key="both_halves_under15", name="Both Halves Under 1.5",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_both_halves_under15_home, evaluate_away=eval_both_halves_under15_away,
    ),
    "odd_total_ft": MarketPreset(
        key="odd_total_ft", name="Odd Total Goals",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_odd_total_home, evaluate_away=eval_odd_total_away,
    ),
    "hsh_1h": MarketPreset(
        key="hsh_1h", name="Highest Scoring Half (1st Half)",
        match_type=MatchType.FLEXIBLE_OR, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_hsh_1h_home, evaluate_away=eval_hsh_1h_away,
    ),
    "htft_home_home": MarketPreset(
        key="htft_home_home", name="HT/FT Home-Home",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_htft_hh_home, evaluate_away=eval_htft_hh_away,
    ),
    "htft_draw_home": MarketPreset(
        key="htft_draw_home", name="HT Draw → Home Win",
        match_type=MatchType.FLEXIBLE_OR, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_htft_dh_home, evaluate_away=eval_htft_dh_away,
    ),
    # === MULTISCORE GROUPS ===
    "ms_home_nil_low": MarketPreset(
        key="ms_home_nil_low", name="Multiscore: Home Nil Low (1-0/2-0/3-0)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_home_nil_low_home, evaluate_away=eval_ms_home_nil_low_away,
    ),
    "ms_away_nil_low": MarketPreset(
        key="ms_away_nil_low", name="Multiscore: Away Nil Low (0-1/0-2/0-3)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_away_nil_low_home, evaluate_away=eval_ms_away_nil_low_away,
    ),
    "ms_home_blowout": MarketPreset(
        key="ms_home_blowout", name="Multiscore: Home Blowout (4-0/5-0/6-0)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_home_blowout_home, evaluate_away=eval_ms_home_blowout_away,
    ),
    "ms_away_blowout": MarketPreset(
        key="ms_away_blowout", name="Multiscore: Away Blowout (0-4/0-5/0-6)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_away_blowout_home, evaluate_away=eval_ms_away_blowout_away,
    ),
    "ms_home_comfort": MarketPreset(
        key="ms_home_comfort", name="Multiscore: Home Comfortable (2-1/3-1/4-1)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_home_comfort_home, evaluate_away=eval_ms_home_comfort_away,
    ),
    "ms_away_comfort": MarketPreset(
        key="ms_away_comfort", name="Multiscore: Away Comfortable (1-2/1-3/1-4)",
        match_type=MatchType.COMPLEMENTARY, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_away_comfort_home, evaluate_away=eval_ms_away_comfort_away,
    ),
    "ms_high_home": MarketPreset(
        key="ms_high_home", name="Multiscore: High-Score Home (3-2/4-2/4-3/5-1)",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_high_home_home, evaluate_away=eval_ms_high_home_away,
    ),
    "ms_high_away": MarketPreset(
        key="ms_high_away", name="Multiscore: High-Score Away (2-3/2-4/3-4/1-5)",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_high_away_home, evaluate_away=eval_ms_high_away_away,
    ),
    "ms_draw": MarketPreset(
        key="ms_draw", name="Multiscore: Draw",
        match_type=MatchType.SAME_PATTERN, streak_type=StreakType.OCCURRENCE,
        evaluate_home=eval_ms_draw_home, evaluate_away=eval_ms_draw_away,
    ),
    # === EVENT-BASED (evaluated via fixture_events query in streak_scanner.py,
    #     not the standard evaluate_home/evaluate_away dispatch) ===
    "no_goal_5min": MarketPreset(
        key="no_goal_5min", name="No Goal in First 5 Minutes",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=None,
        evaluate_away=None,
    ),
    "no_goal_10min": MarketPreset(
        key="no_goal_10min", name="No Goal in First 10 Minutes",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=None,
        evaluate_away=None,
    ),
    # === SESSION 5B: STATS-BASED MARKETS (corners, yellow cards) ===
    # match_type=COMBINED (not CROSS_COMPLEMENTARY): no cross defensive/offensive
    # evaluators exist for corners/cards, so tagging them CROSS_COMPLEMENTARY
    # would silently behave identically to COMBINED but display a misleading
    # match type in the spreadsheet/Telegram output.
    "over_8_5_corners": MarketPreset(
        key="over_8_5_corners", name="Over 8.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_corners_total, threshold=8.5),
        evaluate_away=partial(eval_over_corners_total, threshold=8.5),
        stats_based=True, stats_column="corners", stats_threshold=8.5, stats_over=True,
    ),
    "under_8_5_corners": MarketPreset(
        key="under_8_5_corners", name="Under 8.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_corners_total, threshold=8.5),
        evaluate_away=partial(eval_under_corners_total, threshold=8.5),
        stats_based=True, stats_column="corners", stats_threshold=8.5, stats_over=False,
    ),
    "over_9_5_corners": MarketPreset(
        key="over_9_5_corners", name="Over 9.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_corners_total, threshold=9.5),
        evaluate_away=partial(eval_over_corners_total, threshold=9.5),
        stats_based=True, stats_column="corners", stats_threshold=9.5, stats_over=True,
    ),
    "under_9_5_corners": MarketPreset(
        key="under_9_5_corners", name="Under 9.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_corners_total, threshold=9.5),
        evaluate_away=partial(eval_under_corners_total, threshold=9.5),
        stats_based=True, stats_column="corners", stats_threshold=9.5, stats_over=False,
    ),
    "over_10_5_corners": MarketPreset(
        key="over_10_5_corners", name="Over 10.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_corners_total, threshold=10.5),
        evaluate_away=partial(eval_over_corners_total, threshold=10.5),
        stats_based=True, stats_column="corners", stats_threshold=10.5, stats_over=True,
    ),
    "under_10_5_corners": MarketPreset(
        key="under_10_5_corners", name="Under 10.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_corners_total, threshold=10.5),
        evaluate_away=partial(eval_under_corners_total, threshold=10.5),
        stats_based=True, stats_column="corners", stats_threshold=10.5, stats_over=False,
    ),
    "over_11_5_corners": MarketPreset(
        key="over_11_5_corners", name="Over 11.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_corners_total, threshold=11.5),
        evaluate_away=partial(eval_over_corners_total, threshold=11.5),
        stats_based=True, stats_column="corners", stats_threshold=11.5, stats_over=True,
    ),
    "under_11_5_corners": MarketPreset(
        key="under_11_5_corners", name="Under 11.5 Total Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_corners_total, threshold=11.5),
        evaluate_away=partial(eval_under_corners_total, threshold=11.5),
        stats_based=True, stats_column="corners", stats_threshold=11.5, stats_over=False,
    ),
    # Team corners
    "over_3_5_team_corners": MarketPreset(
        key="over_3_5_team_corners", name="Over 3.5 Team Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_team_stat_home, threshold=3.5),
        evaluate_away=partial(eval_over_team_stat_away, threshold=3.5),
        stats_based=True, stats_column="corners", stats_threshold=3.5, stats_over=True,
    ),
    "under_3_5_team_corners": MarketPreset(
        key="under_3_5_team_corners", name="Under 3.5 Team Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_team_stat_home, threshold=3.5),
        evaluate_away=partial(eval_under_team_stat_away, threshold=3.5),
        stats_based=True, stats_column="corners", stats_threshold=3.5, stats_over=False,
    ),
    "over_4_5_team_corners": MarketPreset(
        key="over_4_5_team_corners", name="Over 4.5 Team Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_team_stat_home, threshold=4.5),
        evaluate_away=partial(eval_over_team_stat_away, threshold=4.5),
        stats_based=True, stats_column="corners", stats_threshold=4.5, stats_over=True,
    ),
    "under_4_5_team_corners": MarketPreset(
        key="under_4_5_team_corners", name="Under 4.5 Team Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_team_stat_home, threshold=4.5),
        evaluate_away=partial(eval_under_team_stat_away, threshold=4.5),
        stats_based=True, stats_column="corners", stats_threshold=4.5, stats_over=False,
    ),
    "over_5_5_team_corners": MarketPreset(
        key="over_5_5_team_corners", name="Over 5.5 Team Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_team_stat_home, threshold=5.5),
        evaluate_away=partial(eval_over_team_stat_away, threshold=5.5),
        stats_based=True, stats_column="corners", stats_threshold=5.5, stats_over=True,
    ),
    "under_5_5_team_corners": MarketPreset(
        key="under_5_5_team_corners", name="Under 5.5 Team Corners",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_team_stat_home, threshold=5.5),
        evaluate_away=partial(eval_under_team_stat_away, threshold=5.5),
        stats_based=True, stats_column="corners", stats_threshold=5.5, stats_over=False,
    ),
    # === STATS-BASED: YELLOW CARDS ===
    "over_2_5_cards": MarketPreset(
        key="over_2_5_cards", name="Over 2.5 Total Cards",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_corners_total, threshold=2.5),
        evaluate_away=partial(eval_over_corners_total, threshold=2.5),
        stats_based=True, stats_column="yellow_cards", stats_threshold=2.5, stats_over=True,
    ),
    "under_2_5_cards": MarketPreset(
        key="under_2_5_cards", name="Under 2.5 Total Cards",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_corners_total, threshold=2.5),
        evaluate_away=partial(eval_under_corners_total, threshold=2.5),
        stats_based=True, stats_column="yellow_cards", stats_threshold=2.5, stats_over=False,
    ),
    "over_3_5_cards": MarketPreset(
        key="over_3_5_cards", name="Over 3.5 Total Cards",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_corners_total, threshold=3.5),
        evaluate_away=partial(eval_over_corners_total, threshold=3.5),
        stats_based=True, stats_column="yellow_cards", stats_threshold=3.5, stats_over=True,
    ),
    "under_3_5_cards": MarketPreset(
        key="under_3_5_cards", name="Under 3.5 Total Cards",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_corners_total, threshold=3.5),
        evaluate_away=partial(eval_under_corners_total, threshold=3.5),
        stats_based=True, stats_column="yellow_cards", stats_threshold=3.5, stats_over=False,
    ),
    # Team cards
    "over_1_5_team_cards": MarketPreset(
        key="over_1_5_team_cards", name="Over 1.5 Team Cards",
        match_type=MatchType.COMBINED, streak_type=StreakType.OCCURRENCE,
        evaluate_home=partial(eval_over_team_stat_home, threshold=1.5),
        evaluate_away=partial(eval_over_team_stat_away, threshold=1.5),
        stats_based=True, stats_column="yellow_cards", stats_threshold=1.5, stats_over=True,
    ),
    "under_1_5_team_cards": MarketPreset(
        key="under_1_5_team_cards", name="Under 1.5 Team Cards",
        match_type=MatchType.COMBINED, streak_type=StreakType.NON_OCCURRENCE,
        evaluate_home=partial(eval_under_team_stat_home, threshold=1.5),
        evaluate_away=partial(eval_under_team_stat_away, threshold=1.5),
        stats_based=True, stats_column="yellow_cards", stats_threshold=1.5, stats_over=False,
    ),
}


def get_market(key: str) -> Optional[MarketPreset]:
    """Retrieve a market preset by key."""
    return CORE_MARKETS.get(key)


def get_all_markets() -> Dict[str, MarketPreset]:
    """Return all registered market presets."""
    return CORE_MARKETS.copy()
