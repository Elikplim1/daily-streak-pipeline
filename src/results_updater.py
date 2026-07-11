"""
Results Updater — fetches actual match results for completed fixtures.

Finds fixtures in Supabase where:
  - status = 'NS' (not started)
  - kickoff_utc < NOW() - INTERVAL '3 hours' (kicked off long enough ago
    that it can't still be in play — a fresh kickoff might still be live)
  - source_match_id IS NOT NULL (can query API)

Queries API-Football for the actual result. Only fixtures whose reported
status is genuinely terminal get written back — the fixtures.status column
has a CHECK constraint (NS, LIVE, HT, FT, AET, PEN, PST, CANC, ABD, AWD)
that does NOT permit '1H', '2H', 'ET', 'P', 'BT', 'WO', 'SUSP', or 'INT',
so any in-play or not-yet-legal status is left alone (counted as
still_pending) rather than attempted — writing one of those would violate
the constraint. Runs BEFORE the Results Validator in the pipeline
(Phase 0.5).

API cost: 1 call per fixture. Capped per run via RESULTS_UPDATE_LIMIT (env,
default 200) — fixture_ingester has only ever looked back 1 day, so the
backlog of stale NS fixtures can be large; an unbounded run risks the CI
timeout and burning the daily API quota in one go. Oldest-first ordering
means the backlog clears gradually across runs rather than all-or-nothing.
"""
import logging
import os
import time
import requests
from typing import List

from src.config import API_FOOTBALL_KEY
from src.db import get_connection

logger = logging.getLogger(__name__)

API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

# Statuses treated as "voided" — the match won't produce a real result.
# Limited to values the fixtures_status_check CHECK constraint actually
# permits; 'WO'/'SUSP'/'INT' are not legal column values, so those are
# left as still_pending instead (see module docstring).
VOID_STATUSES = ("PST", "CANC", "ABD", "AWD")
COMPLETED_STATUSES = ("FT", "AET", "PEN")
# Statuses safe to write via update_fixture_result() — anything else
# (in-play, or a status the CHECK constraint doesn't allow) is skipped.
TERMINAL_STATUSES = COMPLETED_STATUSES + VOID_STATUSES


def get_stale_fixtures(cursor, limit: int) -> List[dict]:
    """
    Find fixtures past their kickoff (with a 3-hour buffer so matches that
    just kicked off aren't mistaken for stale) that still show NS, oldest
    first, capped at `limit` per call.
    Returns list of {id, source_match_id, kickoff_utc}.
    """
    cursor.execute("""
        SELECT id, source_match_id, kickoff_utc
        FROM fixtures
        WHERE status = 'NS'
          AND kickoff_utc < NOW() - INTERVAL '3 hours'
          AND source_match_id IS NOT NULL
        ORDER BY kickoff_utc ASC
        LIMIT %s
    """, (limit,))
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def fetch_fixture_result(source_match_id: int) -> dict:
    """
    Fetch a single fixture's result from API-Football.
    Returns the fixture dict or empty dict on failure.
    """
    url = f"{API_BASE}/fixtures"
    params = {"id": source_match_id}

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        errors = data.get("errors")
        if isinstance(errors, dict) and errors:
            logger.warning(f"API error for fixture {source_match_id}: {errors}")
            return {}

        results = data.get("response", [])
        if results:
            return results[0]
        return {}

    except Exception as e:
        logger.error(f"Failed to fetch result for {source_match_id}: {e}")
        return {}


def update_fixture_result(cursor, fixture_uuid: str, api_data: dict) -> str:
    """
    Update a fixture's status and scores from API-Football data.
    Returns the new status string.

    NEVER include sh_home or sh_away in UPDATE — they are GENERATED columns.
    """
    fixture_data = api_data.get("fixture", {})
    goals = api_data.get("goals", {}) or {}
    score = api_data.get("score", {}) or {}

    new_status = fixture_data.get("status", {}).get("short", "NS")
    ft_home = goals.get("home")
    ft_away = goals.get("away")
    ht_scores = score.get("halftime") or {}
    ht_home = ht_scores.get("home")
    ht_away = ht_scores.get("away")

    cursor.execute("""
        UPDATE fixtures SET
            status = %s,
            ft_home = %s,
            ft_away = %s,
            ht_home = %s,
            ht_away = %s,
            updated_at = NOW()
        WHERE id = %s
    """, (new_status, ft_home, ft_away, ht_home, ht_away, fixture_uuid))

    return new_status


def run_results_update() -> dict:
    """
    Main entry: find stale fixtures and update their results.
    Returns summary dict.
    """
    if not API_FOOTBALL_KEY:
        logger.warning("No API_FOOTBALL_KEY — skipping results update")
        return {"stale_found": 0, "updated": 0, "voided": 0, "still_pending": 0, "errors": 0}

    limit = int(os.getenv("RESULTS_UPDATE_LIMIT", "200"))

    summary = {
        "stale_found": 0,
        "updated": 0,
        "voided": 0,
        "still_pending": 0,
        "errors": 0,
    }

    with get_connection() as conn:
        cursor = conn.cursor()
        stale = get_stale_fixtures(cursor, limit)
        summary["stale_found"] = len(stale)

        if not stale:
            logger.info("No stale fixtures to update")
            return summary

        logger.info(f"Found {len(stale)} stale fixtures to update (limit={limit})")

        for fixture in stale:
            try:
                cursor.execute("SAVEPOINT result_sp")

                api_data = fetch_fixture_result(int(fixture["source_match_id"]))

                if not api_data:
                    summary["errors"] += 1
                    cursor.execute("ROLLBACK TO SAVEPOINT result_sp")
                    continue

                reported_status = api_data.get("fixture", {}).get("status", {}).get("short", "NS")

                if reported_status not in TERMINAL_STATUSES:
                    # In-play or otherwise non-terminal — do NOT attempt the
                    # UPDATE (the CHECK constraint doesn't allow most in-play
                    # codes anyway). Leave the fixture as-is for a later run.
                    summary["still_pending"] += 1
                    cursor.execute("RELEASE SAVEPOINT result_sp")
                    time.sleep(0.5)
                    continue

                new_status = update_fixture_result(
                    cursor, str(fixture["id"]), api_data
                )

                cursor.execute("RELEASE SAVEPOINT result_sp")

                if new_status in COMPLETED_STATUSES:
                    summary["updated"] += 1
                else:
                    summary["voided"] += 1

                # Rate limit courtesy
                time.sleep(0.5)

            except Exception as e:
                cursor.execute("ROLLBACK TO SAVEPOINT result_sp")
                summary["errors"] += 1
                logger.error(f"Error updating fixture {fixture.get('source_match_id')}: {e}")

        conn.commit()

    logger.info(
        f"Results update: {summary['updated']} completed, "
        f"{summary['voided']} voided, {summary['still_pending']} pending, "
        f"{summary['errors']} errors"
    )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    run_results_update()
