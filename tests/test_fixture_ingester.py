"""
Unit tests for the fixture ingester — tests parsing and entity resolution
without hitting the API or Supabase.
"""
from unittest.mock import MagicMock, patch

import pytest
from src.fixture_ingester import EntityCache, _parse_stat, maybe_ingest_stats, run_ingestion


class TestEntityCache:
    def test_empty_cache(self):
        cache = EntityCache()
        assert len(cache.leagues) == 0
        assert len(cache.teams) == 0

    def test_league_cache_lookup(self):
        cache = EntityCache()
        cache.leagues[39] = "uuid-premier-league"
        assert cache.leagues.get(39) == "uuid-premier-league"
        assert cache.leagues.get(999) is None

    def test_team_cache_lookup(self):
        cache = EntityCache()
        cache.teams[33] = "uuid-man-utd"
        assert cache.teams.get(33) == "uuid-man-utd"
        assert cache.teams.get(9999) is None

    def test_cache_update(self):
        cache = EntityCache()
        cache.leagues[39] = "old-uuid"
        cache.leagues[39] = "new-uuid"
        assert cache.leagues[39] == "new-uuid"


class TestAPIResponseParsing:
    """Test parsing of API-Football response structures."""

    SAMPLE_FIXTURE = {
        "fixture": {
            "id": 1234567,
            "date": "2026-06-27T14:00:00+00:00",
            "status": {"short": "NS"},
        },
        "league": {
            "id": 39, "name": "Premier League",
            "country": "England", "season": 2025,
        },
        "teams": {
            "home": {"id": 33, "name": "Manchester United", "logo": ""},
            "away": {"id": 34, "name": "Newcastle", "logo": ""},
        },
        "goals": {"home": None, "away": None},
        "score": {
            "halftime": {"home": None, "away": None},
            "fulltime": {"home": None, "away": None},
        },
    }

    COMPLETED_FIXTURE = {
        "fixture": {
            "id": 1234568,
            "date": "2026-06-26T14:00:00+00:00",
            "status": {"short": "FT"},
        },
        "league": {
            "id": 244, "name": "Veikkausliiga",
            "country": "Finland", "season": 2026,
        },
        "teams": {
            "home": {"id": 1001, "name": "HJK Helsinki", "logo": ""},
            "away": {"id": 1002, "name": "KuPS", "logo": ""},
        },
        "goals": {"home": 2, "away": 1},
        "score": {
            "halftime": {"home": 1, "away": 0},
            "fulltime": {"home": 2, "away": 1},
        },
    }

    def test_parse_upcoming_fixture_status(self):
        f = self.SAMPLE_FIXTURE
        assert f["fixture"]["status"]["short"] == "NS"

    def test_parse_upcoming_fixture_null_goals(self):
        f = self.SAMPLE_FIXTURE
        assert f["goals"]["home"] is None
        assert f["goals"]["away"] is None

    def test_parse_upcoming_fixture_league(self):
        f = self.SAMPLE_FIXTURE
        assert f["league"]["id"] == 39
        assert f["league"]["name"] == "Premier League"

    def test_parse_completed_fixture_status(self):
        f = self.COMPLETED_FIXTURE
        assert f["fixture"]["status"]["short"] == "FT"

    def test_parse_completed_fixture_goals(self):
        f = self.COMPLETED_FIXTURE
        assert f["goals"]["home"] == 2
        assert f["goals"]["away"] == 1

    def test_parse_completed_fixture_halftime(self):
        f = self.COMPLETED_FIXTURE
        assert f["score"]["halftime"]["home"] == 1
        assert f["score"]["halftime"]["away"] == 0

    def test_extract_source_match_id(self):
        f = self.SAMPLE_FIXTURE
        assert f["fixture"]["id"] == 1234567

    def test_extract_source_match_id_as_str(self):
        f = self.SAMPLE_FIXTURE
        assert str(f["fixture"]["id"]) == "1234567"

    def test_extract_league_source_id(self):
        f = self.SAMPLE_FIXTURE
        assert f["league"]["id"] == 39

    def test_extract_team_source_ids(self):
        f = self.SAMPLE_FIXTURE
        assert f["teams"]["home"]["id"] == 33
        assert f["teams"]["away"]["id"] == 34

    def test_extract_season_as_str(self):
        f = self.COMPLETED_FIXTURE
        season = str(f["league"]["season"]) if f["league"].get("season") else None
        assert season == "2026"

    def test_null_score_dict_handling(self):
        # When score is null/None-like
        fixture = dict(self.SAMPLE_FIXTURE)
        fixture["goals"] = None
        goals = fixture.get("goals", {}) or {}
        assert goals.get("home") is None

    def test_null_halftime_dict_handling(self):
        fixture = dict(self.SAMPLE_FIXTURE)
        fixture["score"] = {"halftime": None, "fulltime": None}
        score = fixture.get("score", {}) or {}
        ht = score.get("halftime") or {}
        assert ht.get("home") is None

    def test_entity_type_coercion(self):
        # ensure_league/team expect int, API returns int
        f = self.SAMPLE_FIXTURE
        assert isinstance(f["league"]["id"], int)
        assert isinstance(f["teams"]["home"]["id"], int)


class TestParseStat:
    """_parse_stat: handles None, ints, and percentage strings from the API."""

    def test_none_value(self):
        assert _parse_stat({'Fouls': None}, 'Fouls') is None

    def test_missing_key(self):
        assert _parse_stat({}, 'Fouls') is None

    def test_plain_int(self):
        assert _parse_stat({'Total Shots': 12}, 'Total Shots') == 12

    def test_percentage_string(self):
        assert _parse_stat({'Ball Possession': '55%'}, 'Ball Possession') == 55.0

    def test_percentage_string_with_whitespace(self):
        assert _parse_stat({'Passes %': ' 87% '}, 'Passes %') == 87.0

    def test_empty_string(self):
        assert _parse_stat({'Fouls': ''}, 'Fouls') is None

    def test_non_numeric_string(self):
        assert _parse_stat({'Fouls': 'N/A'}, 'Fouls') is None

    def test_decimal_string(self):
        assert _parse_stat({'expected_goals': '1.83'}, 'expected_goals') == 1.83


class TestMaybeIngestStats:
    """maybe_ingest_stats: skip-if-exists, venue_split resolution, unknown-team handling."""

    def test_skips_if_stats_already_exist(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)  # count > 0
        cache = EntityCache()

        result = maybe_ingest_stats(cursor, 'fixture-uuid', '12345', cache, home_team_api_id=33)

        assert result is False
        assert cursor.execute.call_count == 1  # only the existence check ran

    @patch('src.fixture_ingester.fetch_fixture_stats')
    def test_skips_if_api_returns_no_stats(self, mock_fetch):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)
        mock_fetch.return_value = []
        cache = EntityCache()

        result = maybe_ingest_stats(cursor, 'fixture-uuid', '12345', cache, home_team_api_id=33)

        assert result is False

    @patch('src.fixture_ingester.fetch_fixture_stats')
    def test_inserts_stats_with_correct_venue_split(self, mock_fetch):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)
        mock_fetch.return_value = [
            {
                'team': {'id': 34, 'name': 'Away FC'},  # API order != home-first
                'statistics': [{'type': 'Ball Possession', 'value': '40%'}],
            },
            {
                'team': {'id': 33, 'name': 'Home FC'},
                'statistics': [
                    {'type': 'Ball Possession', 'value': '60%'},
                    {'type': 'Corner Kicks', 'value': 5},
                ],
            },
        ]
        cache = EntityCache()
        cache.teams[33] = 'home-uuid'
        cache.teams[34] = 'away-uuid'

        result = maybe_ingest_stats(cursor, 'fixture-uuid', '12345', cache, home_team_api_id=33)

        assert result is True
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if 'INSERT INTO fixture_stats_football' in c[0][0]
        ]
        assert len(insert_calls) == 2

        by_team_uuid = {c[0][1][1]: c[0][1] for c in insert_calls}
        assert by_team_uuid['away-uuid'][2] == 'away'  # venue_split
        assert by_team_uuid['home-uuid'][2] == 'home'
        assert by_team_uuid['home-uuid'][0] == 'fixture-uuid'

    @patch('src.fixture_ingester.fetch_fixture_stats')
    def test_skips_unknown_team_without_crashing(self, mock_fetch):
        cursor = MagicMock()
        cursor.fetchone.return_value = (0,)
        mock_fetch.return_value = [
            {'team': {'id': 999, 'name': 'Unknown FC'}, 'statistics': []},
        ]
        cache = EntityCache()  # empty — team 999 not resolvable

        result = maybe_ingest_stats(cursor, 'fixture-uuid', '12345', cache, home_team_api_id=999)

        assert result is True  # loop ran, just produced no inserts
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if 'INSERT INTO fixture_stats_football' in c[0][0]
        ]
        assert len(insert_calls) == 0


class TestRunIngestionSavepointIsolation:
    """A single fixture failure must not poison the rest of the date's batch.

    Mocks the whole DB layer (get_connection, EntityCache) and API layer
    (fetch_fixtures_by_date, upsert_fixture) so this exercises the actual
    savepoint sequencing in run_ingestion()'s loop without a real database.
    """

    def _make_api_fixture(self, fixture_id):
        return {
            "fixture": {"id": fixture_id, "date": "2026-07-08T12:00:00+00:00", "status": {"short": "NS"}},
            "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2026},
            "teams": {
                "home": {"id": 100, "name": "Home FC", "logo": ""},
                "away": {"id": 200, "name": "Away FC", "logo": ""},
            },
            "goals": {"home": None, "away": None},
            "score": {"halftime": {"home": None, "away": None}, "fulltime": {"home": None, "away": None}},
        }

    @patch('src.fixture_ingester.time.sleep')
    @patch('src.fixture_ingester.upsert_fixture')
    @patch('src.fixture_ingester.fetch_fixtures_by_date')
    @patch('src.fixture_ingester.get_connection')
    @patch.object(EntityCache, 'load_from_db')
    def test_failed_fixture_does_not_block_the_next_one(
        self, mock_load_cache, mock_get_connection, mock_fetch_dates, mock_upsert, mock_sleep,
    ):
        cursor = MagicMock()
        cursor.fetchone.return_value = None  # "existed" check: not found, for both fixtures
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        bad_fixture = self._make_api_fixture(111)
        good_fixture = self._make_api_fixture(222)
        mock_fetch_dates.return_value = [bad_fixture, good_fixture]

        # First upsert raises (simulating a DB error mid-INSERT); second succeeds.
        mock_upsert.side_effect = [Exception("simulated INSERT failure"), "new-fixture-uuid"]

        summary = run_ingestion(days_back=0, days_forward=0)

        # The failing fixture is counted as an error, but the good one still
        # gets processed and counted — proving isolation between the two.
        assert summary["errors"] == 1
        assert summary["fixtures_inserted"] == 1

        executed_sql = [c[0][0] for c in cursor.execute.call_args_list]
        savepoint_calls = [s for s in executed_sql if 'SAVEPOINT' in s]
        # One SAVEPOINT + one terminator (RELEASE or ROLLBACK TO) per fixture.
        assert savepoint_calls.count('SAVEPOINT fixture_sp') == 2
        assert 'ROLLBACK TO SAVEPOINT fixture_sp' in savepoint_calls
        assert 'RELEASE SAVEPOINT fixture_sp' in savepoint_calls

        # The rollback must come before the second fixture's own SAVEPOINT —
        # i.e. the transaction was un-aborted before moving on.
        first_savepoint_idx = savepoint_calls.index('SAVEPOINT fixture_sp')
        rollback_idx = savepoint_calls.index('ROLLBACK TO SAVEPOINT fixture_sp')
        second_savepoint_idx = len(savepoint_calls) - 1 - savepoint_calls[::-1].index('SAVEPOINT fixture_sp')
        assert first_savepoint_idx < rollback_idx < second_savepoint_idx

    @patch('src.fixture_ingester.time.sleep')
    @patch('src.fixture_ingester.upsert_fixture')
    @patch('src.fixture_ingester.fetch_fixtures_by_date')
    @patch('src.fixture_ingester.get_connection')
    @patch.object(EntityCache, 'load_from_db')
    def test_successful_fixture_releases_its_savepoint(
        self, mock_load_cache, mock_get_connection, mock_fetch_dates, mock_upsert, mock_sleep,
    ):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        mock_fetch_dates.return_value = [self._make_api_fixture(333)]
        mock_upsert.return_value = "new-fixture-uuid"

        summary = run_ingestion(days_back=0, days_forward=0)

        assert summary["errors"] == 0
        assert summary["fixtures_inserted"] == 1

        executed_sql = [c[0][0] for c in cursor.execute.call_args_list]
        assert 'RELEASE SAVEPOINT fixture_sp' in executed_sql
        assert 'ROLLBACK TO SAVEPOINT fixture_sp' not in executed_sql

    @patch('src.fixture_ingester.time.sleep')
    @patch('src.fixture_ingester.upsert_fixture')
    @patch('src.fixture_ingester.fetch_fixtures_by_date')
    @patch('src.fixture_ingester.get_connection')
    @patch.object(EntityCache, 'load_from_db')
    def test_upsert_returning_none_rolls_back_not_releases(
        self, mock_load_cache, mock_get_connection, mock_fetch_dates, mock_upsert, mock_sleep,
    ):
        """upsert_fixture() swallows its own exceptions and returns None
        instead of raising — the transaction may already be aborted in that
        case, so this path must ROLLBACK TO SAVEPOINT, not RELEASE (which
        would itself raise in an aborted transaction and crash the run)."""
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        mock_fetch_dates.return_value = [self._make_api_fixture(444)]
        mock_upsert.return_value = None  # no exception, just a None result

        summary = run_ingestion(days_back=0, days_forward=0)

        assert summary["errors"] == 1
        executed_sql = [c[0][0] for c in cursor.execute.call_args_list]
        assert 'ROLLBACK TO SAVEPOINT fixture_sp' in executed_sql
        assert 'RELEASE SAVEPOINT fixture_sp' not in executed_sql
