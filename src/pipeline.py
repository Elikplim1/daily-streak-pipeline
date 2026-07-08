"""
Pipeline Orchestrator — ETL for daily streak scanning.

Flow:
1. EXTRACT:   Get upcoming fixtures from Supabase
2. TRANSFORM: Run streak scanner + correlation checker
3. LOAD:      Write results to flagged_opportunities table
4. NOTIFY:    Format Telegram message (shadow mode = log only)
"""
import json
import logging
import uuid
from datetime import datetime
from typing import List

from src.config import SHADOW_MODE, SCAN_MARKETS, API_FOOTBALL_KEY
from src.db import get_connection, get_cursor
from src.streak_scanner import scan_all_upcoming, FixtureScanResult
from src.correlation_checker import apply_alignment
from src.market_presets import CORE_MARKETS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

_INSERT_SQL = """
    INSERT INTO flagged_opportunities (
        fixture_id, scan_date, league_id, league_name,
        home_team_id, home_team_name, away_team_id, away_team_name,
        fixture_date, market_key, market_name, match_type, streak_type,
        home_venue_streak, home_overall_streak,
        away_venue_streak, away_overall_streak,
        signal_tier, alignment_met,
        shadow_mode, telegram_payload, pipeline_run_id
    ) VALUES (
        %s, CURRENT_DATE, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s,
        %s, %s,
        %s, %s,
        %s, %s, %s
    )
    ON CONFLICT (fixture_id, market_key, scan_date)
    DO UPDATE SET
        home_venue_streak   = EXCLUDED.home_venue_streak,
        home_overall_streak = EXCLUDED.home_overall_streak,
        away_venue_streak   = EXCLUDED.away_venue_streak,
        away_overall_streak = EXCLUDED.away_overall_streak,
        signal_tier         = EXCLUDED.signal_tier,
        alignment_met       = EXCLUDED.alignment_met,
        telegram_payload    = EXCLUDED.telegram_payload,
        pipeline_run_id     = EXCLUDED.pipeline_run_id
"""


def load_results_to_supabase(
    scan_results: List[FixtureScanResult],
    pipeline_run_id: str,
) -> tuple[int, int]:
    """
    Write all scan results to the flagged_opportunities table.

    Writes ALL tiers (HIGH_SIGNAL, MODERATE_SIGNAL, TRACKING) so the user
    sees the full strength landscape. Uses INSERT … ON CONFLICT for idempotent re-runs.

    Returns:
        (rows_written, errors)
    """
    rows_written = 0
    errors = 0

    with get_connection() as conn:
        cursor = conn.cursor()

        for fixture_result in scan_results:
            for mkey, mdata in fixture_result.market_results.items():
                if mkey not in SCAN_MARKETS:
                    continue

                market = CORE_MARKETS[mkey]
                home_venue = mdata['home_venue']
                home_overall = mdata['home_overall']
                away_venue = mdata['away_venue']
                away_overall = mdata['away_overall']

                telegram_payload = {
                    'fixture': f"{fixture_result.home_team_name} vs {fixture_result.away_team_name}",
                    'market': market.name,
                    'signal': mdata['signal_tier'],
                    'home_venue_streak': home_venue.streak_length,
                    'home_venue_trend': home_venue.trend_count,
                    'home_overall_streak': home_overall.streak_length,
                    'home_overall_trend': home_overall.trend_count,
                    'away_venue_streak': away_venue.streak_length,
                    'away_venue_trend': away_venue.trend_count,
                    'away_overall_streak': away_overall.streak_length,
                    'away_overall_trend': away_overall.trend_count,
                    'alignment': mdata['alignment_met'],
                    'date': fixture_result.fixture_date,
                }

                try:
                    cursor.execute(_INSERT_SQL, (
                        fixture_result.fixture_id,
                        fixture_result.league_id,
                        fixture_result.league_name,
                        fixture_result.home_team_id,
                        fixture_result.home_team_name,
                        fixture_result.away_team_id,
                        fixture_result.away_team_name,
                        fixture_result.fixture_date,
                        mkey,
                        market.name,
                        market.match_type,
                        market.streak_type,
                        home_venue.streak_length,
                        home_overall.streak_length,
                        away_venue.streak_length,
                        away_overall.streak_length,
                        mdata['signal_tier'],
                        mdata['alignment_met'],
                        SHADOW_MODE,
                        json.dumps(telegram_payload),
                        pipeline_run_id,
                    ))
                    rows_written += 1
                except Exception as e:
                    errors += 1
                    logger.error(
                        f"Error writing {mkey} for fixture {fixture_result.fixture_id}: {e}"
                    )

        conn.commit()

    logger.info(f"Loaded {rows_written} rows to flagged_opportunities ({errors} errors)")
    return rows_written, errors


def run_pipeline(days_ahead: int = None) -> None:
    """
    Main pipeline entry point.

    days_ahead defaults to the DAYS_AHEAD env var (default 7) so GitHub
    Actions can override it without code changes.

    1. EXTRACT + TRANSFORM: streak scan of upcoming fixtures
    2. TRANSFORM: correlation / alignment checks
    3. LOAD: write to flagged_opportunities (ON CONFLICT upsert)
    4. NOTIFY: Telegram summary + HIGH_SIGNAL alerts (shadow mode safe)
    """
    import os
    if days_ahead is None:
        days_ahead = int(os.getenv('DAYS_AHEAD', '3'))

    pipeline_run_id = (
        f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )
    logger.info(f"=== Pipeline Run: {pipeline_run_id} ===")
    logger.info(f"Shadow Mode: {'ON' if SHADOW_MODE else 'OFF'}")
    logger.info(f"Markets: {SCAN_MARKETS}")
    logger.info(f"Scan window: {days_ahead} days ahead")

    # Phase 0: INGEST new fixtures from API-Football
    import os
    ingest_enabled = os.getenv("INGEST_ENABLED", "true").lower() == "true"
    if ingest_enabled and API_FOOTBALL_KEY:
        logger.info("Phase 0: Ingesting fixtures from API-Football...")
        from src.fixture_ingester import run_ingestion
        ingest_summary = run_ingestion(days_back=1, days_forward=days_ahead)
        logger.info(
            f"Ingestion complete: {ingest_summary['fixtures_inserted']} new, "
            f"{ingest_summary['fixtures_updated']} updated, "
            f"{ingest_summary['new_leagues_created']} new leagues, "
            f"{ingest_summary['new_teams_created']} new teams"
        )
    else:
        logger.info("Phase 0: Fixture ingestion skipped (INGEST_ENABLED=false or no API key)")

    # Phase 1: EXTRACT + TRANSFORM (streak scan)
    logger.info("Phase 1: Scanning upcoming fixtures for streaks...")
    scan_results = scan_all_upcoming(days_ahead)

    if not scan_results:
        logger.info("No upcoming fixtures found. Pipeline complete.")
        return

    # Phase 2: TRANSFORM (alignment)
    logger.info("Phase 2: Applying correlation checks...")
    scan_results = apply_alignment(scan_results)

    # Phase 3: LOAD
    logger.info("Phase 3: Loading results to Supabase...")
    rows_written, errors = load_results_to_supabase(scan_results, pipeline_run_id)

    # Phase 4: NOTIFY
    high_signals = [
        (fr, mkey, md)
        for fr in scan_results
        for mkey, md in fr.market_results.items()
        if md['signal_tier'] == 'HIGH_SIGNAL'
    ]
    moderate_signals = [
        (fr, mkey, md)
        for fr in scan_results
        for mkey, md in fr.market_results.items()
        if md['signal_tier'] == 'MODERATE_SIGNAL'
    ]
    tracking_count = sum(
        1 for fr in scan_results
        for md in fr.market_results.values()
        if md['signal_tier'] == 'TRACKING'
    )

    logger.info("=== Run Complete ===")
    logger.info(f"Fixtures scanned:  {len(scan_results)}")
    logger.info(f"HIGH_SIGNAL:       {len(high_signals)}")
    logger.info(f"MODERATE_SIGNAL:   {len(moderate_signals)}")
    logger.info(f"Rows written:      {rows_written}")

    from src.telegram_notifier import send_alerts
    send_alerts(
        high_signals=high_signals,
        total_fixtures=len(scan_results),
        high_count=len(high_signals),
        moderate_count=len(moderate_signals),
        tracking_count=tracking_count,
        rows_written=rows_written,
        pipeline_run_id=pipeline_run_id,
    )

    # Step 5: SPREADSHEET EXPORT
    from src.config import SPREADSHEET_ENABLED
    if SPREADSHEET_ENABLED:
        from src.spreadsheet_exporter import build_spreadsheet, send_telegram_document
        filepath = build_spreadsheet(scan_results, pipeline_run_id)
        if filepath:
            caption = (
                f"📊 STREAK Signals — {len(scan_results)} fixtures scanned\n"
                f"🔴 {len(high_signals)} HIGH | 🟡 {len(moderate_signals)} MODERATE\n"
                f"Run: {pipeline_run_id}"
            )
            send_telegram_document(filepath, caption)

    logger.info(f"=== Pipeline Run Complete: {pipeline_run_id} ===")


if __name__ == '__main__':
    run_pipeline()
