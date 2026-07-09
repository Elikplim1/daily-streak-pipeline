"""
Unit tests for pipeline.py's pipeline_runs health-table wiring:
start_pipeline_run / complete_pipeline_run / fail_pipeline_run, and the
try/except around run_pipeline() that records + re-raises failures.
"""
from unittest.mock import MagicMock, patch

import pytest
from src.pipeline import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
    run_pipeline,
)


def _mock_connection(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    ctx.__exit__.return_value = False
    return ctx


class TestStartPipelineRun:
    @patch('src.pipeline.get_connection')
    def test_inserts_running_row_with_expected_params(self, mock_get_connection):
        cursor = MagicMock()
        mock_get_connection.return_value = _mock_connection(cursor)

        start_pipeline_run('run_123', days_ahead=3, ingest_enabled=True)

        sql, params = cursor.execute.call_args[0]
        assert "INSERT INTO pipeline_runs" in sql
        assert "'RUNNING'" in sql
        assert params[0] == 'run_123'
        assert params[2] == 3       # days_ahead
        assert params[3] is True    # ingest_enabled
        assert params[4] > 0        # markets_count (len(SCAN_MARKETS))


class TestCompletePipelineRun:
    @patch('src.pipeline.get_connection')
    def test_updates_complete_status_and_counts(self, mock_get_connection):
        cursor = MagicMock()
        mock_get_connection.return_value = _mock_connection(cursor)

        complete_pipeline_run(
            'run_123',
            fixtures_scanned=50, high_signal=3, moderate_signal=7, tracking=40,
            rows_written=100, write_errors=0,
            telegram_summary_sent=True, telegram_alerts_sent=True, telegram_error=None,
            spreadsheet_sent=True,
        )

        sql, params = cursor.execute.call_args[0]
        assert "status = 'COMPLETE'" in sql
        assert "completed_at = NOW()" in sql
        assert params[-1] == 'run_123'  # WHERE id = %s is the last param

    @patch('src.pipeline.get_connection')
    def test_omitted_counts_default_to_none(self, mock_get_connection):
        """Fields not passed should bind as None (column keeps its own DB default)."""
        cursor = MagicMock()
        mock_get_connection.return_value = _mock_connection(cursor)

        complete_pipeline_run('run_123', fixtures_scanned=10)

        _, params = cursor.execute.call_args[0]
        # fixtures_scanned is the 5th column in the fixed order; everything
        # else omitted should be None.
        assert params.count(None) == len(params) - 2  # fixtures_scanned + id are non-None


class TestFailPipelineRun:
    @patch('src.pipeline.get_connection')
    def test_updates_failed_status_with_error_message(self, mock_get_connection):
        cursor = MagicMock()
        mock_get_connection.return_value = _mock_connection(cursor)

        fail_pipeline_run('run_123', 'boom: connection refused')

        sql, params = cursor.execute.call_args[0]
        assert "status = 'FAILED'" in sql
        assert params[0] == 'boom: connection refused'
        assert params[1] == 'run_123'

    @patch('src.pipeline.get_connection')
    def test_error_message_truncated(self, mock_get_connection):
        cursor = MagicMock()
        mock_get_connection.return_value = _mock_connection(cursor)

        fail_pipeline_run('run_123', 'x' * 5000)

        _, params = cursor.execute.call_args[0]
        assert len(params[0]) == 2000

    @patch('src.pipeline.get_connection')
    def test_swallows_its_own_db_errors(self, mock_get_connection):
        """A secondary DB failure while recording the original failure must
        not raise — it would mask the real exception being handled."""
        mock_get_connection.side_effect = Exception("DB unreachable")

        fail_pipeline_run('run_123', 'original error')  # must not raise


class TestRunPipelineFailureHandling:
    @patch('src.pipeline.fail_pipeline_run')
    @patch('src.pipeline.start_pipeline_run')
    @patch('src.pipeline.scan_all_upcoming')
    @patch('src.pipeline.API_FOOTBALL_KEY', '')  # skip Phase 0 (no ingestion)
    def test_exception_is_recorded_and_reraised(
        self, mock_scan, mock_start, mock_fail,
    ):
        mock_scan.side_effect = RuntimeError("streak scan exploded")

        with pytest.raises(RuntimeError, match="streak scan exploded"):
            run_pipeline(days_ahead=3)

        mock_start.assert_called_once()
        mock_fail.assert_called_once()
        fail_args = mock_fail.call_args[0]
        assert fail_args[1] == "streak scan exploded"

    @patch('src.pipeline.complete_pipeline_run')
    @patch('src.pipeline.start_pipeline_run')
    @patch('src.pipeline.scan_all_upcoming')
    @patch('src.pipeline.API_FOOTBALL_KEY', '')
    def test_no_fixtures_still_completes_the_run(
        self, mock_scan, mock_start, mock_complete,
    ):
        mock_scan.return_value = []

        run_pipeline(days_ahead=3)

        mock_start.assert_called_once()
        mock_complete.assert_called_once()
        _, kwargs = mock_complete.call_args
        assert kwargs['fixtures_scanned'] == 0
