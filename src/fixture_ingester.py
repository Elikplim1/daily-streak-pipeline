"""
Daily Fixture Ingester — pulls ALL global fixtures from API-Football.

Runs as Phase 0 in the GitHub Actions pipeline, before the streak scanner.
Uses alias_mapping for entity resolution (no source_team_id/source_league_id columns).
Upserts fixtures via ON CONFLICT (source_match_id).

API cost: ~9 calls per run (1 per date × 9 dates).

Schema notes (confirmed via Step 0):
- fixtures.source_match_id: TEXT, UNIQUE constraint added by this module's setup
- leagues: no source_league_id column; use alias_mapping (entity_type='league')
- teams: no source_team_id column; use alias_mapping (entity_type='team')
- alias_mapping.uq_alias: UNIQUE (entity_type, alias_source, alias_value)
- sh_home, sh_away: GENERATED ALWAYS — never in INSERT/UPDATE
"""
import logging
import time
import uuid
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.config import API_FOOTBALL_KEY, API_FOOTBALL_BASE_URL
from src.db import get_connection

logger = logging.getLogger(__name__)

HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}


# ─── API Layer ───────────────────────────────────────────────────────

def fetch_fixtures_by_date(date_str: str) -> List[dict]:
    """
    Fetch ALL fixtures globally for a given date from API-Football.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        List of fixture dicts from the API response, or [] on error/limit
    """
    url = f"{API_FOOTBALL_BASE_URL}/fixtures"
    params = {"date": date_str}

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        errors = data.get("errors", {})
        if isinstance(errors, dict) and errors:
            logger.error(f"API error for {date_str}: {errors}")
            return []
        if isinstance(errors, list) and errors:
            logger.error(f"API error for {date_str}: {errors}")
            return []

        results = data.get("response", [])
        remaining = resp.headers.get("x-ratelimit-requests-remaining", "?")
        logger.info(
            f"Fetched {len(results)} fixtures for {date_str} "
            f"(API calls remaining: {remaining})"
        )

        if len(results) == 0:
            logger.warning(
                f"Zero fixtures returned for {date_str} — "
                f"may indicate the daily API limit is exhausted"
            )

        return results

    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {date_str}: {e}")
        return []


# ─── Entity Cache ────────────────────────────────────────────────────

class EntityCache:
    """
    In-memory cache of API integer ID → Supabase UUID mappings.

    Pre-loaded from alias_mapping at startup using numeric API IDs only
    (alias_value ~ '^[0-9]+$'). Updated as new entities are created.
    """

    def __init__(self) -> None:
        self.leagues: Dict[int, str] = {}  # api_int_id → UUID
        self.teams: Dict[int, str] = {}    # api_int_id → UUID

    def load_from_db(self, cursor) -> None:
        """Pre-load all numeric API ID mappings from alias_mapping."""
        cursor.execute("""
            SELECT alias_value::int, master_id::text
            FROM alias_mapping
            WHERE entity_type = 'league'
              AND alias_source = 'api_football'
              AND alias_value ~ '^[0-9]+$'
        """)
        for api_id, uuid_str in cursor.fetchall():
            self.leagues[api_id] = uuid_str

        cursor.execute("""
            SELECT alias_value::int, master_id::text
            FROM alias_mapping
            WHERE entity_type = 'team'
              AND alias_source = 'api_football'
              AND alias_value ~ '^[0-9]+$'
        """)
        for api_id, uuid_str in cursor.fetchall():
            self.teams[api_id] = uuid_str

        logger.info(
            f"Cache loaded: {len(self.leagues)} leagues, {len(self.teams)} teams "
            f"(numeric API IDs only)"
        )


# ─── Entity Resolution ───────────────────────────────────────────────

def ensure_league(cursor, cache: EntityCache, api_league: dict) -> str:
    """
    Ensure a league exists in Supabase. Returns the UUID.

    Lookup order:
    1. In-memory cache (fast path)
    2. alias_mapping by numeric API ID
    3. INSERT new league + alias_mapping entry

    Args:
        cursor: psycopg2 cursor
        cache: EntityCache instance
        api_league: league dict from API response (id, name, country, season, ...)

    Returns:
        UUID string of the league
    """
    source_id = int(api_league["id"])

    if source_id in cache.leagues:
        return cache.leagues[source_id]

    cursor.execute("""
        SELECT master_id::text FROM alias_mapping
        WHERE entity_type = 'league'
          AND alias_source = 'api_football'
          AND alias_value = %s
    """, (str(source_id),))
    row = cursor.fetchone()
    if row:
        cache.leagues[source_id] = row[0]
        return row[0]

    new_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO leagues (id, name, country, sport, is_active)
        VALUES (%s, %s, %s, 'football', true)
    """, (
        new_id,
        api_league.get("name", f"League {source_id}"),
        api_league.get("country", "Unknown"),
    ))
    cursor.execute("""
        INSERT INTO alias_mapping
            (entity_type, master_id, alias_source, alias_value, alias_type, confidence)
        VALUES ('league', %s, 'api_football', %s, 'id', 'exact')
        ON CONFLICT (entity_type, alias_source, alias_value) DO NOTHING
    """, (new_id, str(source_id)))

    cache.leagues[source_id] = new_id
    logger.info(f"Created league: {api_league.get('name')} (api_id={source_id})")
    return new_id


def ensure_team(cursor, cache: EntityCache, api_team: dict) -> str:
    """
    Ensure a team exists in Supabase. Returns the UUID.

    Lookup order:
    1. In-memory cache (fast path for numeric-aliased teams)
    2. alias_mapping by numeric API ID
    3. teams.name exact match (fallback for pre-existing teams without numeric alias)
       → adds numeric alias entry so future lookups are fast
    4. INSERT new team + alias_mapping entry

    Args:
        cursor: psycopg2 cursor
        cache: EntityCache instance
        api_team: team dict from API response (id, name, logo)

    Returns:
        UUID string of the team
    """
    source_id = int(api_team["id"])
    name = api_team.get("name", f"Team {source_id}")

    if source_id in cache.teams:
        return cache.teams[source_id]

    cursor.execute("""
        SELECT master_id::text FROM alias_mapping
        WHERE entity_type = 'team'
          AND alias_source = 'api_football'
          AND alias_value = %s
    """, (str(source_id),))
    row = cursor.fetchone()
    if row:
        cache.teams[source_id] = row[0]
        return row[0]

    # Fallback: name match against existing teams
    cursor.execute(
        "SELECT id::text FROM teams WHERE name = %s AND sport = 'football' LIMIT 1",
        (name,)
    )
    row = cursor.fetchone()
    if row:
        team_uuid = row[0]
        # Add numeric alias so future runs skip this fallback
        cursor.execute("""
            INSERT INTO alias_mapping
                (entity_type, master_id, alias_source, alias_value, alias_type, confidence)
            VALUES ('team', %s, 'api_football', %s, 'id', 'exact')
            ON CONFLICT (entity_type, alias_source, alias_value) DO NOTHING
        """, (team_uuid, str(source_id)))
        cache.teams[source_id] = team_uuid
        return team_uuid

    # Create new team
    new_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO teams (id, name, sport, logo_url)
        VALUES (%s, %s, 'football', %s)
    """, (new_id, name, api_team.get("logo", "")))
    cursor.execute("""
        INSERT INTO alias_mapping
            (entity_type, master_id, alias_source, alias_value, alias_type, confidence)
        VALUES ('team', %s, 'api_football', %s, 'id', 'exact')
        ON CONFLICT (entity_type, alias_source, alias_value) DO NOTHING
    """, (new_id, str(source_id)))

    cache.teams[source_id] = new_id
    logger.info(f"Created team: {name} (api_id={source_id})")
    return new_id


# ─── Fixture Upsert ──────────────────────────────────────────────────

def upsert_fixture(cursor, cache: EntityCache, api_fixture: dict) -> Optional[str]:
    """
    Insert or update a single fixture in Supabase.

    Uses source_match_id as the natural key (ON CONFLICT upsert).
    Only updates score/status fields on conflict — never overwrites IDs.

    NEVER includes sh_home, sh_away (GENERATED ALWAYS columns).

    Args:
        cursor: psycopg2 cursor
        cache: EntityCache instance
        api_fixture: fixture dict from API response

    Returns:
        UUID of the upserted fixture, or None on error
    """
    fixture_data = api_fixture["fixture"]
    league_data = api_fixture["league"]
    teams_data = api_fixture["teams"]
    goals = api_fixture.get("goals", {}) or {}
    score = api_fixture.get("score", {}) or {}

    source_match_id = str(fixture_data["id"])
    status = fixture_data["status"]["short"]
    kickoff = fixture_data["date"]

    league_uuid = ensure_league(cursor, cache, league_data)
    home_uuid = ensure_team(cursor, cache, teams_data["home"])
    away_uuid = ensure_team(cursor, cache, teams_data["away"])

    ft_home = goals.get("home")
    ft_away = goals.get("away")
    ht_scores = score.get("halftime") or {}
    ht_home = ht_scores.get("home")
    ht_away = ht_scores.get("away")
    season = str(league_data["season"]) if league_data.get("season") else None

    try:
        cursor.execute("""
            INSERT INTO fixtures (
                id, source_match_id, league_id, season,
                home_team_id, away_team_id,
                ft_home, ft_away, ht_home, ht_away,
                status, kickoff_utc
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (source_match_id) DO UPDATE SET
                ft_home    = EXCLUDED.ft_home,
                ft_away    = EXCLUDED.ft_away,
                ht_home    = EXCLUDED.ht_home,
                ht_away    = EXCLUDED.ht_away,
                status     = EXCLUDED.status,
                updated_at = now()
            RETURNING id
        """, (
            str(uuid.uuid4()), source_match_id, league_uuid, season,
            home_uuid, away_uuid,
            ft_home, ft_away, ht_home, ht_away,
            status, kickoff,
        ))
        result = cursor.fetchone()
        return str(result[0]) if result else None

    except Exception as e:
        logger.error(f"Upsert failed for fixture {source_match_id}: {e}")
        return None


# ─── Main Ingestion Loop ─────────────────────────────────────────────

def run_ingestion(days_back: int = 1, days_forward: int = 7) -> dict:
    """
    Main entry point: ingest fixtures for a date range.

    Default: yesterday through today+7 = 9 API calls.
    Commits after each date batch for crash-safety.

    Args:
        days_back: How many days back to include (for score updates)
        days_forward: How many days ahead to fetch (for upcoming fixtures)

    Returns:
        Summary dict with ingestion counts
    """
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days_back)
    end_date = today + timedelta(days=days_forward)

    logger.info(f"=== Fixture Ingestion: {start_date} to {end_date} ===")

    summary = {
        "dates_queried": 0,
        "api_fixtures_received": 0,
        "new_leagues_created": 0,
        "new_teams_created": 0,
        "fixtures_inserted": 0,
        "fixtures_updated": 0,
        "errors": 0,
    }

    with get_connection() as conn:
        cursor = conn.cursor()

        cache = EntityCache()
        cache.load_from_db(cursor)
        initial_leagues = len(cache.leagues)
        initial_teams = len(cache.teams)

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            summary["dates_queried"] += 1

            fixtures = fetch_fixtures_by_date(date_str)
            summary["api_fixtures_received"] += len(fixtures)

            if not fixtures:
                current_date += timedelta(days=1)
                time.sleep(1)
                continue

            for api_fixture in fixtures:
                try:
                    source_id = str(api_fixture["fixture"]["id"])
                    cursor.execute(
                        "SELECT id FROM fixtures WHERE source_match_id = %s",
                        (source_id,)
                    )
                    existed = cursor.fetchone() is not None

                    result = upsert_fixture(cursor, cache, api_fixture)
                    if result:
                        if existed:
                            summary["fixtures_updated"] += 1
                        else:
                            summary["fixtures_inserted"] += 1
                    else:
                        summary["errors"] += 1

                except Exception as e:
                    summary["errors"] += 1
                    logger.error(f"Error processing fixture: {e}")

            conn.commit()
            logger.info(f"  {date_str}: {len(fixtures)} fixtures processed")

            current_date += timedelta(days=1)
            time.sleep(1)

        summary["new_leagues_created"] = len(cache.leagues) - initial_leagues
        summary["new_teams_created"] = len(cache.teams) - initial_teams

    logger.info("=== Ingestion Complete ===")
    logger.info(f"  Dates queried:     {summary['dates_queried']}")
    logger.info(f"  API fixtures:      {summary['api_fixtures_received']}")
    logger.info(f"  New leagues:       {summary['new_leagues_created']}")
    logger.info(f"  New teams:         {summary['new_teams_created']}")
    logger.info(f"  Fixtures inserted: {summary['fixtures_inserted']}")
    logger.info(f"  Fixtures updated:  {summary['fixtures_updated']}")
    logger.info(f"  Errors:            {summary['errors']}")

    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_ingestion()
