"""
Unit tests for results_updater.py — stale-fixture querying (with the
RESULTS_UPDATE_LIMIT cap), result parsing, and SAVEPOINT isolation.
Mocked cursor/connection/API throughout — no live DB or network.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from src.results_updater import (
    get_stale_fixtures,
    update_fixture_result,
    run_results_update,
    VOID_STATUSES,
    COMPLETED_STATUSES,
)


def make_api_result(status='FT', ft_h=2, ft_a=1, ht_h=1, ht_a=0) -> dict:
    return {
        'fixture': {'status': {'short': status}},
        'goals': {'home': ft_h, 'away': ft_a},
        'score': {'halftime': {'home': ht_h, 'away': ht_a}},
    }


class TestGetStaleFixtures:
    def test_query_includes_limit_param(self):
        cursor = MagicMock()
        cursor.description = [('id',), ('source_match_id',), ('kickoff_utc',)]
        cursor.fetchall.return_value = []

        get_stale_fixtures(cursor, limit=50)

        sql, params = cursor.execute.call_args[0]
        assert 'LIMIT %s' in sql
        assert params == (50,)
        assert "status = 'NS'" in sql
        assert 'ORDER BY kickoff_utc ASC' in sql

    def test_returns_dicts(self):
        cursor = MagicMock()
        cursor.description = [('id',), ('source_match_id',), ('kickoff_utc',)]
        cursor.fetchall.return_value = [('fx-1', '12345', '2026-07-01')]

        rows = get_stale_fixtures(cursor, limit=200)

        assert rows == [{'id': 'fx-1', 'source_match_id': '12345', 'kickoff_utc': '2026-07-01'}]


class TestUpdateFixtureResult:
    def test_completed_fixture_updates_scores_and_status(self):
        cursor = MagicMock()
        api_data = make_api_result(status='FT', ft_h=3, ft_a=1, ht_h=2, ht_a=0)

        new_status = update_fixture_result(cursor, 'fixture-uuid', api_data)

        assert new_status == 'FT'
        sql, params = cursor.execute.call_args[0]
        assert 'UPDATE fixtures SET' in sql
        assert 'sh_home' not in sql  # GENERATED column must never be touched
        assert 'sh_away' not in sql
        assert params == ('FT', 3, 1, 2, 0, 'fixture-uuid')

    def test_void_status_still_updates(self):
        cursor = MagicMock()
        api_data = make_api_result(status='PST', ft_h=None, ft_a=None, ht_h=None, ht_a=None)

        new_status = update_fixture_result(cursor, 'fixture-uuid', api_data)

        assert new_status == 'PST'
        assert new_status in VOID_STATUSES

    def test_missing_score_dict_handled(self):
        cursor = MagicMock()
        api_data = {'fixture': {'status': {'short': 'NS'}}, 'goals': {}, 'score': {}}

        new_status = update_fixture_result(cursor, 'fixture-uuid', api_data)

        assert new_status == 'NS'


class TestRunResultsUpdate:
    @patch('src.results_updater.API_FOOTBALL_KEY', '')
    def test_skips_when_no_api_key(self):
        summary = run_results_update()
        assert summary == {"stale_found": 0, "updated": 0, "voided": 0, "still_pending": 0, "errors": 0}

    @patch('src.results_updater.time.sleep')
    @patch('src.results_updater.fetch_fixture_result')
    @patch('src.results_updater.get_connection')
    @patch('src.results_updater.API_FOOTBALL_KEY', 'fake-key')
    def test_uses_limit_from_env(self, mock_get_connection, mock_fetch, mock_sleep):
        cursor = MagicMock()
        cursor.description = [('id',), ('source_match_id',), ('kickoff_utc',)]
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        with patch.dict(os.environ, {'RESULTS_UPDATE_LIMIT': '25'}):
            run_results_update()

        sql, params = cursor.execute.call_args[0]
        assert params == (25,)

    @patch('src.results_updater.time.sleep')
    @patch('src.results_updater.fetch_fixture_result')
    @patch('src.results_updater.get_connection')
    @patch('src.results_updater.API_FOOTBALL_KEY', 'fake-key')
    def test_failed_fetch_does_not_block_next_fixture(self, mock_get_connection, mock_fetch, mock_sleep):
        cursor = MagicMock()
        cursor.description = [('id',), ('source_match_id',), ('kickoff_utc',)]
        cursor.fetchall.return_value = [
            ('fx-1', '111', '2026-07-01'),
            ('fx-2', '222', '2026-07-02'),
        ]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        # First fixture: API returns nothing (failure). Second: succeeds.
        mock_fetch.side_effect = [{}, make_api_result(status='FT')]

        summary = run_results_update()

        assert summary['stale_found'] == 2
        assert summary['errors'] == 1
        assert summary['updated'] == 1

        executed_sql = [c[0][0] for c in cursor.execute.call_args_list]
        assert executed_sql.count('SAVEPOINT result_sp') == 2
        assert 'ROLLBACK TO SAVEPOINT result_sp' in executed_sql
        assert 'RELEASE SAVEPOINT result_sp' in executed_sql

    @patch('src.results_updater.time.sleep')
    @patch('src.results_updater.fetch_fixture_result')
    @patch('src.results_updater.get_connection')
    @patch('src.results_updater.API_FOOTBALL_KEY', 'fake-key')
    def test_classifies_completed_voided_and_pending(self, mock_get_connection, mock_fetch, mock_sleep):
        cursor = MagicMock()
        cursor.description = [('id',), ('source_match_id',), ('kickoff_utc',)]
        cursor.fetchall.return_value = [
            ('fx-1', '111', '2026-07-01'),
            ('fx-2', '222', '2026-07-01'),
            ('fx-3', '333', '2026-07-01'),
        ]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        mock_fetch.side_effect = [
            make_api_result(status='FT'),
            make_api_result(status='PST'),
            make_api_result(status='NS'),  # postponed to a new date, still not started
        ]

        summary = run_results_update()

        assert summary['updated'] == 1
        assert summary['voided'] == 1
        assert summary['still_pending'] == 1

    def test_status_partitions_are_disjoint(self):
        assert set(VOID_STATUSES) & set(COMPLETED_STATUSES) == set()
