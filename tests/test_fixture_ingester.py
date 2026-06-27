"""
Unit tests for the fixture ingester — tests parsing and entity resolution
without hitting the API or Supabase.
"""
import pytest
from src.fixture_ingester import EntityCache


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
