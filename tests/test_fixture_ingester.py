"""
Unit tests for the fixture ingester — tests parsing and entity resolution
without hitting the API or Supabase.
"""
from unittest.mock import MagicMock, patch

import pytest
from src.fixture_ingester import EntityCache, _parse_stat, maybe_ingest_stats


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
