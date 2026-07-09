"""
Phase 2: The Alignment — Correlation Checker.

After the streak scanner labels each team's streak per market, this module checks
whether the HOME team's streak and AWAY team's streak ALIGN according to the market's
match_type rule.

Alignment Rules:
- COMPLEMENTARY: Home shows pattern X AND away shows pattern Y (complement already
  encoded in evaluate_away). Both must hit HIGH_SIGNAL_MIN.
- SAME_PATTERN: Both teams show the SAME pattern individually at HIGH_SIGNAL_MIN.
- COMBINED: Both teams individually exhibit the pattern at HIGH_SIGNAL_MIN.
- FLEXIBLE_OR: EITHER team shows the pattern at HIGH_SIGNAL_MIN.

Signal Tier Logic (uses the STRONGER of venue-specific vs overall per team):
- HIGH_SIGNAL:    alignment confirmed AND (home_best >= 5 OR away_best >= 5)
- MODERATE_SIGNAL: home_best >= 4 OR away_best >= 4
- TRACKING:       below thresholds on both lenses for both teams
"""
import logging
from typing import List

from src.streak_scanner import FixtureScanResult, StreakResult
from src.market_presets import MatchType, CORE_MARKETS
from src.config import (
    HIGH_SIGNAL_MIN,
    MODERATE_SIGNAL_MIN,
    MARKET_THRESHOLD_OVERRIDES,
    SUPPORTING_EVIDENCE_ONLY,
)

logger = logging.getLogger(__name__)


def best_streak(venue: StreakResult, overall: StreakResult) -> int:
    """Return the stronger streak length between venue-specific and overall."""
    return max(venue.streak_length, overall.streak_length)


def best_trend(venue: StreakResult, overall: StreakResult) -> int:
    """Return the stronger trend count between venue-specific and overall."""
    return max(venue.trend_count, overall.trend_count)


def check_alignment(
    home_venue: StreakResult,
    home_overall: StreakResult,
    away_venue: StreakResult,
    away_overall: StreakResult,
    match_type: str,
    market_data: dict = None,
) -> bool:
    """
    Check if the alignment condition is met for a given market.

    Uses the BEST (highest) streak from either lens per team.
    Alignment requires both sides to meet HIGH_SIGNAL_MIN for most types.

    CROSS_COMPLEMENTARY additionally requires the cross_defensive/cross_offensive
    streaks (computed by streak_scanner.scan_fixture, passed via market_data) to
    both meet MODERATE_SIGNAL_MIN — regular alignment confirms the total-goals
    pattern, cross alignment confirms it's backed by matching offense/defense
    records. Falls back to regular-only if cross data isn't present (e.g. the
    market has no cross evaluators wired).
    """
    home_best = best_streak(home_venue, home_overall)
    away_best = best_streak(away_venue, away_overall)

    if match_type in (MatchType.COMPLEMENTARY, MatchType.SAME_PATTERN, MatchType.COMBINED):
        return home_best >= HIGH_SIGNAL_MIN and away_best >= HIGH_SIGNAL_MIN

    elif match_type == MatchType.FLEXIBLE_OR:
        return home_best >= HIGH_SIGNAL_MIN or away_best >= HIGH_SIGNAL_MIN

    elif match_type == MatchType.CROSS_COMPLEMENTARY:
        regular_aligned = home_best >= HIGH_SIGNAL_MIN and away_best >= HIGH_SIGNAL_MIN

        cross_def = market_data.get('cross_defensive') if market_data else None
        cross_off = market_data.get('cross_offensive') if market_data else None

        if cross_def and cross_off:
            cross_aligned = (
                cross_def.streak_length >= MODERATE_SIGNAL_MIN
                and cross_off.streak_length >= MODERATE_SIGNAL_MIN
            )
            return regular_aligned and cross_aligned
        else:
            return regular_aligned

    else:
        logger.warning(f"Unknown match_type: {match_type}")
        return False


def classify_signal_tier(
    home_venue: StreakResult,
    home_overall: StreakResult,
    away_venue: StreakResult,
    away_overall: StreakResult,
    alignment_met: bool,
    market_key: str = "",
) -> str:
    """
    Classify the signal tier based on streak strengths and alignment.

    Markets in SUPPORTING_EVIDENCE_ONLY (config.py) never fire independently —
    they're still calculated and shown in the spreadsheet as context, but
    always classify as TRACKING regardless of streak length or alignment.

    Markets listed in MARKET_THRESHOLD_OVERRIDES (config.py) use their own
    high/moderate thresholds instead of the global HIGH_SIGNAL_MIN /
    MODERATE_SIGNAL_MIN — these are markets where NON_OCCURRENCE is the
    natural baseline, so the default bar is too easy to clear by chance.

    Returns one of: 'HIGH_SIGNAL', 'MODERATE_SIGNAL', 'TRACKING'.
    """
    # Supporting evidence markets never fire independently
    if market_key in SUPPORTING_EVIDENCE_ONLY:
        return 'TRACKING'

    # Stats-based markets (corners, cards) need a minimum sample size — stats
    # data is sparse (only ~4,000 fixtures have it), so a "streak" built on
    # 1-2 matches isn't a reliable signal.
    market = CORE_MARKETS.get(market_key)
    if market and market.stats_based:
        window_sizes = (
            home_venue.window_size, home_overall.window_size,
            away_venue.window_size, away_overall.window_size,
        )
        if min(window_sizes) < 3:
            return 'TRACKING'

    home_best = best_streak(home_venue, home_overall)
    away_best = best_streak(away_venue, away_overall)

    overrides = MARKET_THRESHOLD_OVERRIDES.get(market_key)
    high_min = overrides['high'] if overrides else HIGH_SIGNAL_MIN
    moderate_min = overrides['moderate'] if overrides else MODERATE_SIGNAL_MIN

    if alignment_met and (home_best >= high_min or away_best >= high_min):
        return 'HIGH_SIGNAL'

    if home_best >= moderate_min or away_best >= moderate_min:
        return 'MODERATE_SIGNAL'

    return 'TRACKING'


def apply_alignment(scan_results: List[FixtureScanResult]) -> List[FixtureScanResult]:
    """
    Apply correlation checks to all scanned fixtures.

    For each fixture × market, evaluates alignment and assigns signal tiers.
    Modifies scan_results in-place and returns them.
    """
    for fixture_result in scan_results:
        for mkey, market_data in fixture_result.market_results.items():
            market = CORE_MARKETS[mkey]

            home_venue = market_data['home_venue']
            home_overall = market_data['home_overall']
            away_venue = market_data['away_venue']
            away_overall = market_data['away_overall']

            alignment = check_alignment(
                home_venue, home_overall,
                away_venue, away_overall,
                market.match_type,
                market_data=market_data,
            )
            tier = classify_signal_tier(
                home_venue, home_overall,
                away_venue, away_overall,
                alignment,
                market_key=mkey,
            )

            market_data['alignment_met'] = alignment
            market_data['signal_tier'] = tier

    high_count = sum(
        1 for fr in scan_results
        for md in fr.market_results.values()
        if md['signal_tier'] == 'HIGH_SIGNAL'
    )
    moderate_count = sum(
        1 for fr in scan_results
        for md in fr.market_results.values()
        if md['signal_tier'] == 'MODERATE_SIGNAL'
    )
    logger.info(
        f"Alignment complete: {high_count} HIGH_SIGNAL, {moderate_count} MODERATE_SIGNAL "
        f"across {len(scan_results)} fixtures × {len(CORE_MARKETS)} markets"
    )

    return scan_results
