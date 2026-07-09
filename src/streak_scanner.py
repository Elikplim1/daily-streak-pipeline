"""
Phase 1: The Filter — Venue-Split Streak Scanner.

For each upcoming fixture × each market, evaluates:
- Home team: Home-only streak + Overall streak
- Away team: Away-only streak + Overall streak

"Streak" = consecutive matching outcomes counting backward from the most recent match.
"Trend"  = total matching outcomes within the window (regardless of order).

Supabase column names (confirmed via Step 0 schema discovery):
  fixtures: id (UUID), home_team_id, away_team_id, league_id,
            source_match_id, kickoff_utc, status,
            ft_home, ft_away, ht_home, ht_away, sh_home, sh_away
  teams:    id (UUID), name
  leagues:  id (UUID), name
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Dict, Optional, Tuple

from src.db import get_cursor
from src.market_presets import CORE_MARKETS, MarketPreset, MatchType
from src.config import STREAK_WINDOW

logger = logging.getLogger(__name__)


@dataclass
class StreakResult:
    """Result of evaluating one market for one team from one venue lens."""
    market_key: str
    team_id: str               # UUID string
    venue_lens: str            # 'home_only', 'away_only', or 'overall'
    streak_length: int         # Consecutive True from most recent (0 to STREAK_WINDOW)
    trend_count: int           # Total True in window (0 to STREAK_WINDOW)
    window_size: int           # How many matches were available (may be < STREAK_WINDOW)
    matches_evaluated: List[Optional[bool]] = field(default_factory=list)


@dataclass
class FixtureScanResult:
    """Complete scan result for one fixture across all markets."""
    fixture_id: str            # UUID string (fixtures.id)
    source_match_id: str
    league_id: str             # UUID string
    league_name: str
    home_team_id: str          # UUID string
    home_team_name: str
    away_team_id: str          # UUID string
    away_team_name: str
    fixture_date: str          # ISO format
    market_results: Dict[str, dict] = field(default_factory=dict)
    # market_results[market_key] = {
    #   'home_venue':   StreakResult,
    #   'home_overall': StreakResult,
    #   'away_venue':   StreakResult,
    #   'away_overall': StreakResult,
    #   'signal_tier':  str,
    #   'alignment_met': bool,
    # }


def calculate_streak_and_trend(
    evaluations: List[Optional[bool]]
) -> Tuple[int, int]:
    """
    Given a list of boolean evaluations (newest first), return (streak, trend).

    streak = consecutive True values from index 0 (None values skipped).
    trend  = total True values in the list (None values skipped).

    Examples:
      [True, True, False, True, True] -> streak=2, trend=4
      [True, True, True, True, True]  -> streak=5, trend=5
      [False, True, True, True, True] -> streak=0, trend=4
      [True, None, True, True, True]  -> streak=4, trend=4
    """
    valid = [e for e in evaluations if e is not None]
    if not valid:
        return 0, 0

    streak = 0
    for result in valid:
        if result:
            streak += 1
        else:
            break

    trend = sum(1 for r in valid if r)
    return streak, trend


def get_team_recent_fixtures(
    team_id: str,
    venue_filter: Optional[str],
    limit: int,
    cursor,
) -> List[dict]:
    """
    Query completed fixtures for a team, ordered newest-first.

    Args:
        team_id:      UUID of the team (fixtures.home_team_id / away_team_id)
        venue_filter: 'home' | 'away' | None (all venues)
        limit:        Max matches to return
        cursor:       psycopg2 cursor

    Returns:
        List of fixture dicts, most recent first.
    """
    if venue_filter == 'home':
        team_clause = "home_team_id = %s"
        params: tuple = (team_id, limit)
    elif venue_filter == 'away':
        team_clause = "away_team_id = %s"
        params = (team_id, limit)
    else:
        team_clause = "(home_team_id = %s OR away_team_id = %s)"
        params = (team_id, team_id, limit)

    query = f"""
        SELECT
            id,
            source_match_id,
            league_id,
            home_team_id,
            away_team_id,
            ft_home,
            ft_away,
            ht_home,
            ht_away,
            sh_home,
            sh_away,
            kickoff_utc,
            status
        FROM fixtures
        WHERE status IN ('FT', 'AET', 'PEN')
          AND {team_clause}
          AND ft_home IS NOT NULL
          AND ft_away IS NOT NULL
        ORDER BY kickoff_utc DESC
        LIMIT %s
    """
    cursor.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_team_recent_stats(
    team_id: str,
    venue_filter: Optional[str],
    limit: int,
    cursor,
    stat_column: str = 'corners',
) -> List[dict]:
    """
    Query fixture_stats_football for a team's recent stats (Session 5B).
    Returns fixture dicts augmented with 'home_stat'/'away_stat' columns.

    Only returns fixtures that HAVE stats data for BOTH teams (inner join).
    The uq_fixture_team_period (fixture_id, team_id, period) unique constraint
    on fixture_stats_football guarantees at most one row per side, so this
    join can't fan out into duplicate rows.
    """
    if venue_filter == 'home':
        venue_clause = "f.home_team_id = %s"
    elif venue_filter == 'away':
        venue_clause = "f.away_team_id = %s"
    else:
        venue_clause = "(f.home_team_id = %s OR f.away_team_id = %s)"

    query = f"""
        SELECT f.id as fixture_id, f.home_team_id, f.away_team_id,
               f.ft_home, f.ft_away, f.ht_home, f.ht_away,
               f.kickoff_utc,
               home_stats.{stat_column} as home_stat,
               away_stats.{stat_column} as away_stat
        FROM fixtures f
        JOIN fixture_stats_football home_stats
            ON f.id = home_stats.fixture_id
            AND home_stats.team_id = f.home_team_id
            AND home_stats.period = 'FT'
        JOIN fixture_stats_football away_stats
            ON f.id = away_stats.fixture_id
            AND away_stats.team_id = f.away_team_id
            AND away_stats.period = 'FT'
        WHERE f.status IN ('FT', 'AET', 'PEN')
          AND {venue_clause}
          AND home_stats.{stat_column} IS NOT NULL
          AND away_stats.{stat_column} IS NOT NULL
        ORDER BY f.kickoff_utc DESC
        LIMIT %s
    """

    if venue_filter in ('home', 'away'):
        cursor.execute(query, (team_id, limit))
    else:
        cursor.execute(query, (team_id, team_id, limit))

    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def evaluate_team_market(
    fixtures: List[dict],
    market: MarketPreset,
    team_id: str,
    override_evaluator: Optional[Callable[[dict], Optional[bool]]] = None,
) -> Tuple[int, int, List[Optional[bool]]]:
    """
    Evaluate a market condition across a list of fixtures for one team.

    Determines the team's role per fixture (home/away) from the fixture dict,
    then calls the appropriate evaluate_home or evaluate_away function — or,
    if override_evaluator is given, calls that instead of the market's own
    evaluate_home/evaluate_away (used for CROSS_COMPLEMENTARY cross-streaks,
    where the evaluator differs from the market's regular one).

    Returns:
        (streak_length, trend_count, evaluations_list)
    """
    evaluations = []
    for f in fixtures:
        if f['home_team_id'] == team_id:
            role = 'home'
        elif f['away_team_id'] == team_id:
            role = 'away'
        else:
            evaluations.append(None)
            continue

        if override_evaluator:
            result = override_evaluator(f)
        elif role == 'home':
            result = market.evaluate_home(f)
        else:
            result = market.evaluate_away(f)

        evaluations.append(result)

    streak, trend = calculate_streak_and_trend(evaluations)
    return streak, trend, evaluations


# Event-based markets (Session 5A): evaluated via fixture_events, not the
# fixtures table, so they bypass the standard evaluate_home/evaluate_away
# dispatch. Maps market_key -> minutes_threshold.
EVENT_BASED_MARKETS: Dict[str, int] = {
    'no_goal_5min': 5,
    'no_goal_10min': 10,
}


def evaluate_no_goal_minutes(fixture_id, minutes_threshold, cursor) -> Optional[bool]:
    """Check if there was no goal in the first N minutes of a fixture.

    Includes 'penalty' alongside 'goal'/'own_goal' — scored penalties are
    stored as their own event_type in fixture_events, distinct from
    'missed_pen' (confirmed via Step 0 schema discovery).
    """
    cursor.execute("""
        SELECT COUNT(*) FROM fixture_events
        WHERE fixture_id = %s
          AND event_type IN ('goal', 'own_goal', 'penalty')
          AND minute <= %s
    """, (fixture_id, minutes_threshold))
    goal_count = cursor.fetchone()[0]
    return goal_count == 0  # True = no goal in first N minutes


def evaluate_no_goal_market(
    fixtures: List[dict],
    minutes_threshold: int,
    cursor,
) -> Tuple[int, int, List[Optional[bool]]]:
    """
    Evaluate a 'no goal in first N minutes' market across a list of fixtures.

    Unlike evaluate_team_market, this doesn't depend on which side (home/away)
    the team played in each historical fixture — the market only cares
    whether any goal was scored early, regardless of who scored it.
    """
    evaluations = [
        evaluate_no_goal_minutes(f['id'], minutes_threshold, cursor)
        for f in fixtures
    ]
    streak, trend = calculate_streak_and_trend(evaluations)
    return streak, trend, evaluations


def scan_fixture(fixture: dict, cursor) -> FixtureScanResult:
    """
    Run the complete streak scan for one fixture across all Core markets.

    For each market:
    - Home team: Home-only lens (last N home matches) + Overall (last N any venue)
    - Away team: Away-only lens (last N away matches) + Overall (last N any venue)

    The fixture dict must contain: id, source_match_id, league_id, league_name,
    home_team_id, home_team_name, away_team_id, away_team_name, kickoff_utc.
    """
    home_id = fixture['home_team_id']
    away_id = fixture['away_team_id']

    home_home_fixtures = get_team_recent_fixtures(home_id, 'home', STREAK_WINDOW, cursor)
    home_overall_fixtures = get_team_recent_fixtures(home_id, None, STREAK_WINDOW, cursor)
    away_away_fixtures = get_team_recent_fixtures(away_id, 'away', STREAK_WINDOW, cursor)
    away_overall_fixtures = get_team_recent_fixtures(away_id, None, STREAK_WINDOW, cursor)

    result = FixtureScanResult(
        fixture_id=str(fixture.get('id', '')),
        source_match_id=fixture.get('source_match_id', ''),
        league_id=str(fixture.get('league_id', '')),
        league_name=fixture.get('league_name', ''),
        home_team_id=str(home_id),
        home_team_name=fixture.get('home_team_name', ''),
        away_team_id=str(away_id),
        away_team_name=fixture.get('away_team_name', ''),
        fixture_date=str(fixture.get('kickoff_utc', '')),
    )

    for mkey, market in CORE_MARKETS.items():
        if mkey in EVENT_BASED_MARKETS:
            minutes = EVENT_BASED_MARKETS[mkey]
            h_venue_streak, h_venue_trend, h_venue_evals = evaluate_no_goal_market(
                home_home_fixtures, minutes, cursor
            )
            h_overall_streak, h_overall_trend, h_overall_evals = evaluate_no_goal_market(
                home_overall_fixtures, minutes, cursor
            )
            a_venue_streak, a_venue_trend, a_venue_evals = evaluate_no_goal_market(
                away_away_fixtures, minutes, cursor
            )
            a_overall_streak, a_overall_trend, a_overall_evals = evaluate_no_goal_market(
                away_overall_fixtures, minutes, cursor
            )
            h_venue_window, h_overall_window = len(home_home_fixtures), len(home_overall_fixtures)
            a_venue_window, a_overall_window = len(away_away_fixtures), len(away_overall_fixtures)

        elif market.stats_based:
            # Stats-based markets (corners, cards) query fixture_stats_football
            # instead of fixtures — separate data per lens, not the shared
            # home_home_fixtures/etc. lists used by the other two branches.
            home_home_stats = get_team_recent_stats(
                home_id, 'home', STREAK_WINDOW, cursor, market.stats_column
            )
            home_overall_stats = get_team_recent_stats(
                home_id, None, STREAK_WINDOW, cursor, market.stats_column
            )
            away_away_stats = get_team_recent_stats(
                away_id, 'away', STREAK_WINDOW, cursor, market.stats_column
            )
            away_overall_stats = get_team_recent_stats(
                away_id, None, STREAK_WINDOW, cursor, market.stats_column
            )

            h_venue_streak, h_venue_trend, h_venue_evals = evaluate_team_market(
                home_home_stats, market, home_id
            )
            h_overall_streak, h_overall_trend, h_overall_evals = evaluate_team_market(
                home_overall_stats, market, home_id
            )
            a_venue_streak, a_venue_trend, a_venue_evals = evaluate_team_market(
                away_away_stats, market, away_id
            )
            a_overall_streak, a_overall_trend, a_overall_evals = evaluate_team_market(
                away_overall_stats, market, away_id
            )
            h_venue_window, h_overall_window = len(home_home_stats), len(home_overall_stats)
            a_venue_window, a_overall_window = len(away_away_stats), len(away_overall_stats)

        else:
            h_venue_streak, h_venue_trend, h_venue_evals = evaluate_team_market(
                home_home_fixtures, market, home_id
            )
            h_overall_streak, h_overall_trend, h_overall_evals = evaluate_team_market(
                home_overall_fixtures, market, home_id
            )
            a_venue_streak, a_venue_trend, a_venue_evals = evaluate_team_market(
                away_away_fixtures, market, away_id
            )
            a_overall_streak, a_overall_trend, a_overall_evals = evaluate_team_market(
                away_overall_fixtures, market, away_id
            )
            h_venue_window, h_overall_window = len(home_home_fixtures), len(home_overall_fixtures)
            a_venue_window, a_overall_window = len(away_away_fixtures), len(away_overall_fixtures)

        result.market_results[mkey] = {
            'home_venue': StreakResult(
                market_key=mkey, team_id=str(home_id), venue_lens='home_only',
                streak_length=h_venue_streak, trend_count=h_venue_trend,
                window_size=h_venue_window, matches_evaluated=h_venue_evals,
            ),
            'home_overall': StreakResult(
                market_key=mkey, team_id=str(home_id), venue_lens='overall',
                streak_length=h_overall_streak, trend_count=h_overall_trend,
                window_size=h_overall_window, matches_evaluated=h_overall_evals,
            ),
            'away_venue': StreakResult(
                market_key=mkey, team_id=str(away_id), venue_lens='away_only',
                streak_length=a_venue_streak, trend_count=a_venue_trend,
                window_size=a_venue_window, matches_evaluated=a_venue_evals,
            ),
            'away_overall': StreakResult(
                market_key=mkey, team_id=str(away_id), venue_lens='overall',
                streak_length=a_overall_streak, trend_count=a_overall_trend,
                window_size=a_overall_window, matches_evaluated=a_overall_evals,
            ),
            # Placeholders — filled by correlation_checker
            'signal_tier': 'TRACKING',
            'alignment_met': False,
        }

        # Session 5B: cross-streak calculation for CROSS_COMPLEMENTARY markets.
        # Reuses the already-fetched home_home_fixtures/away_away_fixtures —
        # no extra queries. Only markets with both cross evaluators set
        # (currently the 4 goals markets) get this; corners/cards don't.
        if (
            market.match_type == MatchType.CROSS_COMPLEMENTARY
            and market.evaluate_cross_defensive_home
            and market.evaluate_cross_offensive_away
        ):
            # Home team DEFENSIVE streak (how often they don't concede X at home)
            cross_def_streak, cross_def_trend, _ = evaluate_team_market(
                home_home_fixtures, market, home_id,
                override_evaluator=market.evaluate_cross_defensive_home,
            )
            # Away team OFFENSIVE streak (how often they don't score X away)
            cross_off_streak, cross_off_trend, _ = evaluate_team_market(
                away_away_fixtures, market, away_id,
                override_evaluator=market.evaluate_cross_offensive_away,
            )

            result.market_results[mkey]['cross_defensive'] = StreakResult(
                market_key=mkey, team_id=str(home_id), venue_lens='cross_defensive',
                streak_length=cross_def_streak, trend_count=cross_def_trend,
                window_size=len(home_home_fixtures),
            )
            result.market_results[mkey]['cross_offensive'] = StreakResult(
                market_key=mkey, team_id=str(away_id), venue_lens='cross_offensive',
                streak_length=cross_off_streak, trend_count=cross_off_trend,
                window_size=len(away_away_fixtures),
            )

    return result


def get_upcoming_fixtures(cursor, days_ahead: int = 7) -> List[dict]:
    """
    Fetch fixtures scheduled within the next N days with team and league names.

    Supabase column names: fixtures.id, teams.id, teams.name, leagues.id, leagues.name.
    """
    query = """
        SELECT
            f.id,
            f.source_match_id,
            f.league_id,
            l.name AS league_name,
            f.home_team_id,
            ht.name AS home_team_name,
            f.away_team_id,
            at_.name AS away_team_name,
            f.kickoff_utc
        FROM fixtures f
        JOIN teams ht  ON f.home_team_id = ht.id
        JOIN teams at_ ON f.away_team_id = at_.id
        JOIN leagues l ON f.league_id    = l.id
        WHERE f.status = 'NS'
          AND f.kickoff_utc >= NOW()
          AND f.kickoff_utc <= NOW() + (INTERVAL '1 day' * %s)
        ORDER BY f.kickoff_utc ASC
    """
    cursor.execute(query, (days_ahead,))
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def scan_all_upcoming(days_ahead: int = 7) -> List[FixtureScanResult]:
    """
    Main entry point: scan all upcoming fixtures within the next N days.

    Returns a list of FixtureScanResults with streak data populated but
    alignment/tier fields still set to defaults (run apply_alignment next).
    """
    results = []
    with get_cursor() as cursor:
        upcoming = get_upcoming_fixtures(cursor, days_ahead)
        logger.info(f"Found {len(upcoming)} upcoming fixtures in next {days_ahead} days")

        for i, fixture in enumerate(upcoming):
            try:
                scan_result = scan_fixture(fixture, cursor)
                results.append(scan_result)
                if (i + 1) % 10 == 0:
                    logger.info(f"Scanned {i + 1}/{len(upcoming)} fixtures")
            except Exception as e:
                logger.error(
                    f"Error scanning fixture {fixture.get('id')}: {e}",
                    exc_info=True,
                )

    logger.info(f"Scan complete: {len(results)} fixtures processed")
    return results
