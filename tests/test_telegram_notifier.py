"""
Unit tests for telegram_notifier.py's accuracy summary formatting
(format_accuracy_section), added for the P0 results validator session.
Pure formatting — no Telegram API calls, no DB.
"""
from src.telegram_notifier import format_accuracy_section, build_summary_message


class TestFormatAccuracySection:
    def test_none_when_report_empty(self):
        assert format_accuracy_section({}) is None

    def test_formats_market_names_and_overall(self):
        report = {
            'under_3_5': {'won': 12, 'lost': 3, 'total': 15, 'accuracy': 80.0},
            'gg_ft': {'won': 5, 'lost': 3, 'total': 8, 'accuracy': 62.5},
        }
        section = format_accuracy_section(report)

        assert 'Signal Accuracy (last 7 days)' in section
        assert 'Under 3.5 Goals: 12/15 (80.0%)' in section
        assert 'Both Teams to Score (BTTS): 5/8 (62.5%)' in section
        assert 'Overall: 17/23' in section

    def test_unknown_market_key_falls_back_to_raw_key(self):
        report = {'not_a_real_market': {'won': 1, 'lost': 1, 'total': 2, 'accuracy': 50.0}}
        section = format_accuracy_section(report)
        assert 'not_a_real_market: 1/2 (50.0%)' in section

    def test_sorted_by_total_descending(self):
        report = {
            'ft_win': {'won': 2, 'lost': 0, 'total': 2, 'accuracy': 100.0},
            'gg_ft': {'won': 10, 'lost': 5, 'total': 15, 'accuracy': 66.7},
        }
        section = format_accuracy_section(report)
        gg_idx = section.index('Both Teams to Score')
        ft_idx = section.index('Full-Time Win')
        assert gg_idx < ft_idx  # higher total (15) listed before lower (2)


class TestBuildSummaryMessageWithAccuracy:
    def test_accuracy_section_appended_when_present(self):
        msg = build_summary_message(
            total_fixtures=10, high_count=2, moderate_count=3, tracking_count=5,
            rows_written=10, pipeline_run_id='run_1',
            accuracy_section="\n📈 Signal Accuracy (last 7 days):\n  Overall: 5/10 (50.0%)",
        )
        assert '📈 Signal Accuracy' in msg

    def test_no_accuracy_section_when_none(self):
        msg = build_summary_message(
            total_fixtures=10, high_count=2, moderate_count=3, tracking_count=5,
            rows_written=10, pipeline_run_id='run_1',
            accuracy_section=None,
        )
        assert '📈 Signal Accuracy' not in msg

    def test_backward_compatible_without_accuracy_kwarg(self):
        """Existing callers that don't pass accuracy_section must still work."""
        msg = build_summary_message(
            total_fixtures=10, high_count=2, moderate_count=3, tracking_count=5,
            rows_written=10, pipeline_run_id='run_1',
        )
        assert 'Fixtures scanned: 10' in msg
