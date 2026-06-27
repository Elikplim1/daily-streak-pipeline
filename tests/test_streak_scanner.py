"""
Unit tests for the streak scanner core logic.

Tests calculation functions with known inputs — does NOT require a Supabase connection.
Run with: pytest tests/test_streak_scanner.py -v
"""
import pytest
from src.streak_scanner import calculate_streak_and_trend
from src.market_presets import (
    eval_ft_win_home, eval_ft_win_away,
    eval_btts_home,
    eval_over25_home,
    eval_under25_home,
    eval_hsh_2h_home,
    eval_dc_1x_ft_home,
    eval_dc_x2_ft_home,
    _scores_available,
    _total_goals,
)


class TestStreakAndTrend:
    """Test the core streak/trend calculation."""

    def test_perfect_streak(self):
        evals = [True, True, True, True, True]
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 5
        assert trend == 5

    def test_broken_streak(self):
        evals = [True, True, False, True, True]
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 2
        assert trend == 4

    def test_no_streak(self):
        evals = [False, True, True, True, True]
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 0
        assert trend == 4

    def test_all_false(self):
        evals = [False, False, False, False, False]
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 0
        assert trend == 0

    def test_empty(self):
        streak, trend = calculate_streak_and_trend([])
        assert streak == 0
        assert trend == 0

    def test_with_nones(self):
        """None values (missing data) should be skipped."""
        evals = [True, None, True, True, True]
        # After filtering: [True, True, True, True] → streak=4, trend=4
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 4
        assert trend == 4

    def test_single_match(self):
        evals = [True]
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 1
        assert trend == 1

    def test_trend_higher_than_streak(self):
        evals = [False, True, True, True, True]
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 0
        assert trend == 4

    def test_all_none(self):
        streak, trend = calculate_streak_and_trend([None, None, None])
        assert streak == 0
        assert trend == 0

    def test_none_breaks_streak(self):
        """A None between Trues does NOT break the streak (Nones are skipped)."""
        evals = [True, None, False, True, True]
        # After filtering: [True, False, True, True] → streak=1, trend=3
        streak, trend = calculate_streak_and_trend(evals)
        assert streak == 1
        assert trend == 3


class TestMarketEvaluations:
    """Test individual market evaluation functions."""

    def make_fixture(
        self,
        ft_h=None, ft_a=None,
        ht_h=None, ht_a=None,
    ) -> dict:
        sh_h = (ft_h - ht_h) if ft_h is not None and ht_h is not None else None
        sh_a = (ft_a - ht_a) if ft_a is not None and ht_a is not None else None
        return {
            'ft_home': ft_h, 'ft_away': ft_a,
            'ht_home': ht_h, 'ht_away': ht_a,
            'sh_home': sh_h, 'sh_away': sh_a,
        }

    # ── FT Win ──────────────────────────────────────────────────────────────────

    def test_ft_win_home_win(self):
        f = self.make_fixture(2, 1)
        assert eval_ft_win_home(f) is True

    def test_ft_win_home_lose(self):
        f = self.make_fixture(0, 2)
        assert eval_ft_win_home(f) is False

    def test_ft_win_draw(self):
        f = self.make_fixture(1, 1)
        assert eval_ft_win_home(f) is False

    def test_ft_win_away(self):
        f = self.make_fixture(0, 1)
        assert eval_ft_win_away(f) is True

    def test_ft_win_away_draw(self):
        f = self.make_fixture(2, 2)
        assert eval_ft_win_away(f) is False

    # ── Double Chance 1X ────────────────────────────────────────────────────────

    def test_dc_1x_home_win(self):
        f = self.make_fixture(2, 0)
        assert eval_dc_1x_ft_home(f) is True

    def test_dc_1x_home_draw(self):
        f = self.make_fixture(1, 1)
        assert eval_dc_1x_ft_home(f) is True

    def test_dc_1x_home_lose(self):
        f = self.make_fixture(0, 1)
        assert eval_dc_1x_ft_home(f) is False

    # ── Double Chance X2 ────────────────────────────────────────────────────────

    def test_dc_x2_home_lose(self):
        f = self.make_fixture(0, 1)
        assert eval_dc_x2_ft_home(f) is True

    def test_dc_x2_home_draw(self):
        f = self.make_fixture(1, 1)
        assert eval_dc_x2_ft_home(f) is True

    def test_dc_x2_home_win(self):
        f = self.make_fixture(2, 0)
        assert eval_dc_x2_ft_home(f) is False

    # ── BTTS ────────────────────────────────────────────────────────────────────

    def test_btts_yes(self):
        f = self.make_fixture(2, 1)
        assert eval_btts_home(f) is True

    def test_btts_no_away_blank(self):
        f = self.make_fixture(2, 0)
        assert eval_btts_home(f) is False

    def test_btts_no_home_blank(self):
        f = self.make_fixture(0, 1)
        assert eval_btts_home(f) is False

    # ── Over / Under 2.5 ────────────────────────────────────────────────────────

    def test_over25_yes(self):
        f = self.make_fixture(2, 1)
        assert eval_over25_home(f) is True

    def test_over25_exact_two(self):
        """Exactly 2 goals = NOT over 2.5."""
        f = self.make_fixture(1, 1)
        assert eval_over25_home(f) is False

    def test_under25_yes(self):
        f = self.make_fixture(1, 0)
        assert eval_under25_home(f) is True

    def test_under25_three_goals(self):
        f = self.make_fixture(2, 1)
        assert eval_under25_home(f) is False

    # ── HSH 2nd Half ────────────────────────────────────────────────────────────

    def test_hsh_2h_more_second(self):
        """1H: 0-0, FT: 2-1 → 2H had 3 goals vs 0 in 1H."""
        f = self.make_fixture(2, 1, 0, 0)
        assert eval_hsh_2h_home(f) is True

    def test_hsh_2h_equal(self):
        """1H: 1-1, FT: 2-2 → 2H had 2 goals, 1H had 2 goals → NOT 2H highest."""
        f = self.make_fixture(2, 2, 1, 1)
        assert eval_hsh_2h_home(f) is False

    def test_hsh_2h_more_first(self):
        """1H: 2-1, FT: 2-1 → 2H had 0 goals → NOT 2H highest."""
        f = self.make_fixture(2, 1, 2, 1)
        assert eval_hsh_2h_home(f) is False

    # ── None handling ────────────────────────────────────────────────────────────

    def test_null_scores_ft_win(self):
        f = self.make_fixture(None, None)
        assert eval_ft_win_home(f) is None

    def test_null_scores_btts(self):
        f = self.make_fixture(None, None)
        assert eval_btts_home(f) is None

    def test_null_scores_over25(self):
        f = self.make_fixture(None, None)
        assert eval_over25_home(f) is None

    def test_scores_available_ft(self):
        f = self.make_fixture(2, 1, 1, 0)
        assert _scores_available(f, 'ft') is True

    def test_scores_available_ht(self):
        f = self.make_fixture(2, 1, 1, 0)
        assert _scores_available(f, 'ht') is True

    def test_scores_unavailable_ft(self):
        f = self.make_fixture(None, None)
        assert _scores_available(f, 'ft') is False

    def test_total_goals(self):
        f = self.make_fixture(3, 2)
        assert _total_goals(f) == 5

    def test_total_goals_none(self):
        f = self.make_fixture(None, None)
        assert _total_goals(f) is None
