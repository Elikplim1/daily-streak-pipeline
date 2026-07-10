"""
Results Validator — the P0 feedback loop for the Evidence Intelligence Platform.

For each flagged opportunity where the fixture has now completed:
1. Re-evaluates the market condition against the actual result
2. Records WON/LOST/VOID in signal_outcomes
3. Never modifies the original signal or streak data

Principle: "No component in STREAK is allowed to improve its own score."
This module ONLY measures. It never modifies signals or streaks.
"""
import logging
from datetime import datetime
from typing import Optional

from src.db import get_connection
from src.market_presets import CORE_MARKETS, MatchType

logger = logging.getLogger(__name__)

VOID_STATUSES = ("PST", "CANC", "ABD", "WO")


def evaluate_outcome(market_key: str, fixture: dict) -> Optional[str]:
    """
    Deterministically evaluate whether a market condition was met.

    Args:
        market_key: The market to evaluate
        fixture: Dict with actual scores (ft_home, ft_away, ht_home, ht_away)

    Returns:
        'WON' if the market condition was met
        'LOST' if it was not met
        None if insufficient data to determine, or the market can't be
        evaluated this way (stats-based or event-based markets)
    """
    market = CORE_MARKETS.get(market_key)
    if not market:
        logger.warning(f"Unknown market key: {market_key}")
        return None

    # Stats-based markets (corners, cards) need the stats snapshot, not just
    # scores — not handled by this pass.
    if getattr(market, 'stats_based', False):
        return None

    # Event-based markets (no_goal_5min etc) have no evaluate_home/away —
    # they're evaluated via fixture_events in streak_scanner, not here.
    if market.evaluate_home is None:
        return None

    try:
        if market.match_type == MatchType.FLEXIBLE_OR:
            # FLEXIBLE_OR alignment fires when EITHER side's streak
            # qualifies (see correlation_checker.check_alignment), so the
            # outcome counts as met if either side's condition held in the
            # real result. For most FLEXIBLE_OR markets evaluate_away just
            # calls evaluate_home (identical), so this is a no-op there —
            # it only matters for htft_draw_home, where they're genuinely
            # different, mutually-exclusive conditions ("HT draw then HOME
            # wins" vs "HT draw then AWAY wins").
            home_result = market.evaluate_home(fixture)
            away_result = market.evaluate_away(fixture)
            if home_result is None and away_result is None:
                return None
            result = bool(home_result) or bool(away_result)
        else:
            result = market.evaluate_home(fixture)
            if result is None:
                return None

        return 'WON' if result else 'LOST'
    except Exception as e:
        logger.error(f"Evaluation error for {market_key}: {e}")
        return None


def validate_signals(validation_run_id: str = None) -> dict:
    """
    Main entry: find all flagged signals with completed fixtures,
    evaluate outcomes, and record in signal_outcomes.

    Returns summary dict.
    """
    if validation_run_id is None:
        validation_run_id = f"val_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    summary = {
        "eligible": 0,
        "won": 0,
        "lost": 0,
        "void": 0,
        "skipped": 0,
        "errors": 0,
    }

    with get_connection() as conn:
        cursor = conn.cursor()

        # Find flagged opportunities whose fixtures have completed.
        # Only validate HIGH_SIGNAL and MODERATE_SIGNAL (not TRACKING).
        cursor.execute("""
            SELECT fo.id as fo_id, fo.fixture_id, fo.market_key,
                   fo.signal_tier, fo.home_team_name, fo.away_team_name,
                   fo.league_name, fo.fixture_date, fo.scan_date,
                   fo.home_venue_streak, fo.home_overall_streak,
                   fo.away_venue_streak, fo.away_overall_streak,
                   fo.alignment_met, fo.match_type,
                   f.ft_home, f.ft_away, f.ht_home, f.ht_away,
                   f.status
            FROM flagged_opportunities fo
            JOIN fixtures f ON fo.fixture_id = f.id
            WHERE fo.signal_tier IN ('HIGH_SIGNAL', 'MODERATE_SIGNAL')
              AND f.status IN ('FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD', 'WO')
              AND NOT EXISTS (
                  SELECT 1 FROM signal_outcomes so
                  WHERE so.fixture_id = fo.fixture_id
                    AND so.market_key = fo.market_key
                    AND so.scan_date = fo.scan_date
              )
            ORDER BY fo.fixture_date ASC
        """)

        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        summary["eligible"] = len(rows)

        if not rows:
            logger.info("No new signals to validate")
            return summary

        logger.info(f"Found {len(rows)} signals to validate")

        for row in rows:
            try:
                cursor.execute("SAVEPOINT val_sp")

                fixture_status = row["status"]

                if fixture_status in VOID_STATUSES:
                    outcome = "VOID"
                else:
                    fixture_dict = {
                        "ft_home": row["ft_home"],
                        "ft_away": row["ft_away"],
                        "ht_home": row["ht_home"],
                        "ht_away": row["ht_away"],
                    }
                    if row["ft_home"] is not None and row["ht_home"] is not None:
                        fixture_dict["sh_home"] = row["ft_home"] - row["ht_home"]
                    if row["ft_away"] is not None and row["ht_away"] is not None:
                        fixture_dict["sh_away"] = row["ft_away"] - row["ht_away"]

                    outcome = evaluate_outcome(row["market_key"], fixture_dict)

                    if outcome is None:
                        summary["skipped"] += 1
                        cursor.execute("RELEASE SAVEPOINT val_sp")
                        continue

                # Count only after the write below actually succeeds — counting
                # here (before INSERT) would leave the summary wrong if the
                # INSERT raises and gets rolled back to the savepoint.
                cursor.execute("""
                    INSERT INTO signal_outcomes (
                        flagged_opportunity_id, fixture_id, market_key,
                        signal_tier, home_team_name, away_team_name,
                        league_name, fixture_date, scan_date,
                        home_venue_streak, home_overall_streak,
                        away_venue_streak, away_overall_streak,
                        alignment_met, match_type,
                        outcome_status,
                        home_score_ft, away_score_ft,
                        home_score_ht, away_score_ht,
                        validated_at, validation_run_id
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        NOW(), %s
                    )
                    ON CONFLICT (fixture_id, market_key, scan_date)
                    DO UPDATE SET
                        outcome_status = EXCLUDED.outcome_status,
                        home_score_ft = EXCLUDED.home_score_ft,
                        away_score_ft = EXCLUDED.away_score_ft,
                        validated_at = NOW(),
                        validation_run_id = EXCLUDED.validation_run_id
                """, (
                    row["fo_id"], row["fixture_id"], row["market_key"],
                    row["signal_tier"], row["home_team_name"], row["away_team_name"],
                    row["league_name"], row["fixture_date"], row["scan_date"],
                    row["home_venue_streak"], row["home_overall_streak"],
                    row["away_venue_streak"], row["away_overall_streak"],
                    row["alignment_met"], row["match_type"],
                    outcome, row["ft_home"], row["ft_away"],
                    row["ht_home"], row["ht_away"],
                    validation_run_id,
                ))

                if outcome == "VOID":
                    summary["void"] += 1
                elif outcome == "WON":
                    summary["won"] += 1
                else:
                    summary["lost"] += 1

                cursor.execute("RELEASE SAVEPOINT val_sp")

            except Exception as e:
                cursor.execute("ROLLBACK TO SAVEPOINT val_sp")
                summary["errors"] += 1
                logger.error(f"Validation error for {row.get('market_key')}: {e}")

        conn.commit()

    logger.info(
        f"Validation complete: {summary['won']} WON, {summary['lost']} LOST, "
        f"{summary['void']} VOID, {summary['skipped']} skipped, "
        f"{summary['errors']} errors"
    )
    return summary


def get_accuracy_report(cursor, days: int = None) -> dict:
    """
    Generate accuracy statistics from signal_outcomes.

    Args:
        days: if given, only include outcomes validated in the last N days
            (used for the Telegram "last 7 days" accuracy summary).

    Returns nested dict: {market_key: {won, lost, total, accuracy}}
    """
    if days is not None:
        cursor.execute("""
            SELECT market_key, signal_tier, outcome_status, count(*) as cnt
            FROM signal_outcomes
            WHERE outcome_status IN ('WON', 'LOST')
              AND validated_at >= NOW() - (INTERVAL '1 day' * %s)
            GROUP BY market_key, signal_tier, outcome_status
            ORDER BY market_key, signal_tier
        """, (days,))
    else:
        cursor.execute("""
            SELECT market_key, signal_tier, outcome_status, count(*) as cnt
            FROM signal_outcomes
            WHERE outcome_status IN ('WON', 'LOST')
            GROUP BY market_key, signal_tier, outcome_status
            ORDER BY market_key, signal_tier
        """)

    report = {}
    for row in cursor.fetchall():
        mkey, tier, outcome, cnt = row
        if mkey not in report:
            report[mkey] = {"won": 0, "lost": 0, "total": 0, "accuracy": 0.0}
        if outcome == "WON":
            report[mkey]["won"] += cnt
        elif outcome == "LOST":
            report[mkey]["lost"] += cnt
        report[mkey]["total"] = report[mkey]["won"] + report[mkey]["lost"]
        if report[mkey]["total"] > 0:
            report[mkey]["accuracy"] = round(
                report[mkey]["won"] / report[mkey]["total"] * 100, 1
            )

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    validate_signals()
