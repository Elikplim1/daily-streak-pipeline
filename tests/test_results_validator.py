"""
Unit tests for results_validator.py — deterministic outcome evaluation,
VOID handling, idempotent upserts, and accuracy reporting. Mocked
cursor/connection throughout — no live DB.
"""
from unittest.mock import MagicMock, patch

import pytest
from src.results_validator import evaluate_outcome, validate_signals, get_accuracy_report


def make_fixture(ft_h=None, ft_a=None, ht_h=None, ht_a=None) -> dict:
    return {'ft_home': ft_h, 'ft_away': ft_a, 'ht_home': ht_h, 'ht_away': ht_a}


class TestEvaluateOutcomeStandardMarkets:
    """Markets where evaluate_home alone is the correct outcome check."""

    def test_ft_win_won(self):
        assert evaluate_outcome('ft_win', make_fixture(2, 0)) == 'WON'

    def test_ft_win_lost(self):
        assert evaluate_outcome('ft_win', make_fixture(0, 2)) == 'LOST'

    def test_over_2_5_won(self):
        assert evaluate_outcome('over_2_5', make_fixture(2, 1)) == 'WON'

    def test_under_2_5_lost(self):
        assert evaluate_outcome('under_2_5', make_fixture(2, 1)) == 'LOST'

    def test_gg_ft_same_pattern(self):
        assert evaluate_outcome('gg_ft', make_fixture(1, 1)) == 'WON'
        assert evaluate_outcome('gg_ft', make_fixture(1, 0)) == 'LOST'

    def test_none_when_scores_missing(self):
        assert evaluate_outcome('ft_win', make_fixture(None, None)) is None

    def test_unknown_market_returns_none(self):
        assert evaluate_outcome('not_a_real_market', make_fixture(1, 0)) is None


class TestEvaluateOutcomeSkippedMarkets:
    """Stats-based and event-based markets aren't evaluated this pass."""

    def test_stats_based_market_skipped(self):
        assert evaluate_outcome('over_8_5_corners', make_fixture(2, 1)) is None

    def test_event_based_market_skipped(self):
        assert evaluate_outcome('no_goal_5min', make_fixture(2, 1)) is None


class TestEvaluateOutcomeFlexibleOr:
    """Regression coverage for the FLEXIBLE_OR fix: evaluate_home OR
    evaluate_away, not just evaluate_home. hsh_1h/hsh_2h have identical
    evaluate_home/away so this is a no-op there; htft_draw_home is where
    it actually matters."""

    def test_hsh_2h_identical_functions_unaffected(self):
        # 1H 0-0, FT 2-1: 2nd half had more goals -> True either way.
        f = make_fixture(2, 1, 0, 0)
        assert evaluate_outcome('hsh_2h', f) == 'WON'

    def test_htft_draw_home_wins_after_ht_draw(self):
        """HT draw (1-1), home wins FT (2-1) -> the HOME side's pattern held."""
        f = make_fixture(2, 1, 1, 1)
        assert evaluate_outcome('htft_draw_home', f) == 'WON'

    def test_htft_draw_home_away_wins_after_ht_draw(self):
        """HT draw (1-1), AWAY wins FT (1-2) -> evaluate_home alone would
        say LOST (home didn't win), but the FLEXIBLE_OR market's underlying
        thesis ('either team's draw-then-win streak') was still satisfied
        by the away side. This is the exact case the fix addresses."""
        f = make_fixture(1, 2, 1, 1)
        assert evaluate_outcome('htft_draw_home', f) == 'WON'

    def test_htft_draw_home_no_draw_at_ht(self):
        """No HT draw at all -> neither side's pattern can hold -> LOST."""
        f = make_fixture(2, 1, 1, 0)
        assert evaluate_outcome('htft_draw_home', f) == 'LOST'

    def test_htft_draw_home_draw_stays_draw(self):
        """HT draw, FT also a draw -> neither side actually won -> LOST."""
        f = make_fixture(1, 1, 0, 0)
        assert evaluate_outcome('htft_draw_home', f) == 'LOST'

    def test_htft_draw_home_none_when_scores_missing(self):
        assert evaluate_outcome('htft_draw_home', make_fixture(None, None, None, None)) is None


class TestValidateSignals:
    def _make_row(
        self, fo_id='fo-1', fixture_id='fx-1', market_key='ft_win',
        signal_tier='HIGH_SIGNAL', status='FT', ft_h=2, ft_a=0, ht_h=1, ht_a=0,
    ):
        return (
            fo_id, fixture_id, market_key, signal_tier,
            'Home FC', 'Away FC', 'Premier League', '2026-07-09', '2026-07-09',
            5, 5, 5, 5, True, 'COMPLEMENTARY',
            ft_h, ft_a, ht_h, ht_a, status,
        )

    def _cursor_for_rows(self, rows):
        cursor = MagicMock()
        cols = [
            'fo_id', 'fixture_id', 'market_key', 'signal_tier',
            'home_team_name', 'away_team_name', 'league_name', 'fixture_date', 'scan_date',
            'home_venue_streak', 'home_overall_streak', 'away_venue_streak', 'away_overall_streak',
            'alignment_met', 'match_type',
            'ft_home', 'ft_away', 'ht_home', 'ht_away', 'status',
        ]
        cursor.description = [(c,) for c in cols]
        cursor.fetchall.return_value = rows
        return cursor

    @patch('src.results_validator.get_connection')
    def test_won_signal_recorded(self, mock_get_connection):
        cursor = self._cursor_for_rows([self._make_row(status='FT', ft_h=2, ft_a=0)])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        summary = validate_signals('val_test')

        assert summary['eligible'] == 1
        assert summary['won'] == 1
        assert summary['lost'] == 0
        insert_calls = [c for c in cursor.execute.call_args_list if 'INSERT INTO signal_outcomes' in c[0][0]]
        assert len(insert_calls) == 1
        assert 'ON CONFLICT (fixture_id, market_key, scan_date)' in insert_calls[0][0][0]
        assert 'DO UPDATE' in insert_calls[0][0][0]
        assert insert_calls[0][0][1][15] == 'WON'  # outcome_status positional arg

    @patch('src.results_validator.get_connection')
    def test_void_signal_recorded_without_evaluation(self, mock_get_connection):
        cursor = self._cursor_for_rows([self._make_row(status='PST', ft_h=None, ft_a=None)])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        summary = validate_signals('val_test')

        assert summary['void'] == 1
        insert_calls = [c for c in cursor.execute.call_args_list if 'INSERT INTO signal_outcomes' in c[0][0]]
        assert insert_calls[0][0][1][15] == 'VOID'

    @patch('src.results_validator.get_connection')
    def test_skipped_when_evaluator_returns_none(self, mock_get_connection):
        """A stats-based market's flagged signal has completed but can't be
        evaluated this pass -> skipped, not inserted."""
        cursor = self._cursor_for_rows([self._make_row(market_key='over_8_5_corners', status='FT')])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        summary = validate_signals('val_test')

        assert summary['skipped'] == 1
        insert_calls = [c for c in cursor.execute.call_args_list if 'INSERT INTO signal_outcomes' in c[0][0]]
        assert len(insert_calls) == 0

    @patch('src.results_validator.get_connection')
    def test_no_eligible_rows_returns_zeroed_summary(self, mock_get_connection):
        cursor = self._cursor_for_rows([])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        summary = validate_signals('val_test')
        assert summary == {"eligible": 0, "won": 0, "lost": 0, "void": 0, "skipped": 0, "errors": 0}

    @patch('src.results_validator.get_connection')
    def test_failure_on_one_row_isolated_via_savepoint(self, mock_get_connection):
        cursor = self._cursor_for_rows([
            self._make_row(fixture_id='fx-bad', status='FT'),
            self._make_row(fixture_id='fx-good', status='FT'),
        ])
        # First INSERT raises, second succeeds — simulate via execute side_effect
        call_count = {'n': 0}
        original_execute = cursor.execute

        def flaky_execute(sql, params=None):
            if 'INSERT INTO signal_outcomes' in sql:
                call_count['n'] += 1
                if call_count['n'] == 1:
                    raise Exception("simulated insert failure")
            return MagicMock()

        cursor.execute = MagicMock(side_effect=flaky_execute)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn
        mock_get_connection.return_value.__exit__.return_value = False

        summary = validate_signals('val_test')

        assert summary['errors'] == 1
        assert summary['won'] == 1  # the second (good) row still got counted


class TestGetAccuracyReport:
    def test_computes_won_lost_and_accuracy(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ('ft_win', 'HIGH_SIGNAL', 'WON', 8),
            ('ft_win', 'HIGH_SIGNAL', 'LOST', 2),
            ('under_2_5', 'MODERATE_SIGNAL', 'WON', 3),
        ]

        report = get_accuracy_report(cursor)

        assert report['ft_win'] == {'won': 8, 'lost': 2, 'total': 10, 'accuracy': 80.0}
        assert report['under_2_5'] == {'won': 3, 'lost': 0, 'total': 3, 'accuracy': 100.0}

    def test_empty_report_when_no_outcomes(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        assert get_accuracy_report(cursor) == {}

    def test_days_filter_adds_interval_clause(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []

        get_accuracy_report(cursor, days=7)

        sql, params = cursor.execute.call_args[0]
        assert "INTERVAL '1 day' * %s" in sql
        assert params == (7,)

    def test_no_days_filter_omits_interval_clause(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []

        get_accuracy_report(cursor)

        sql = cursor.execute.call_args[0][0]
        assert 'INTERVAL' not in sql
