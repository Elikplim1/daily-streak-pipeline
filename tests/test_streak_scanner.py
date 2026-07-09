"""
Unit tests for the streak scanner core logic.

Tests calculation functions with known inputs — does NOT require a Supabase connection.
Run with: pytest tests/test_streak_scanner.py -v
"""
from unittest.mock import MagicMock

import pytest
from src.streak_scanner import (
    calculate_streak_and_trend,
    evaluate_no_goal_minutes,
    evaluate_no_goal_market,
    evaluate_team_market,
    get_team_recent_stats,
)
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
    # Session 5A additions
    eval_over15_home, eval_under15_home, eval_over45_home,
    eval_btts_over25_home,
    eval_no_win_nil_home, eval_no_win_nil_away,
    eval_no_home_2plus_home, eval_no_away_2plus_home,
    eval_no_home_3plus_home, eval_no_away_3plus_home,
    eval_no_both_halves_over05_home, eval_both_halves_under15_home,
    eval_odd_total_home, eval_hsh_1h_home, eval_ht_00_home,
    eval_htft_hh_home, eval_htft_hh_away,
    eval_htft_dh_home, eval_htft_dh_away,
    eval_ms_home_nil_low_home, eval_ms_away_nil_low_home,
    eval_ms_home_blowout_home, eval_ms_away_blowout_home,
    eval_ms_home_comfort_home, eval_ms_away_comfort_home,
    eval_ms_high_home_home, eval_ms_high_away_home,
    eval_ms_draw_home,
    CORE_MARKETS,
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


class TestSession5AGoalLineMarkets:
    """Over 1.5 / Under 1.5 / Over 4.5 / BTTS+Over2.5."""

    def make_fixture(self, ft_h=None, ft_a=None, ht_h=None, ht_a=None) -> dict:
        return {'ft_home': ft_h, 'ft_away': ft_a, 'ht_home': ht_h, 'ht_away': ht_a}

    def test_over15_true(self):
        assert eval_over15_home(self.make_fixture(1, 1)) is True

    def test_over15_false_exact(self):
        assert eval_over15_home(self.make_fixture(1, 0)) is False

    def test_over15_none(self):
        assert eval_over15_home(self.make_fixture(None, None)) is None

    def test_under15_true(self):
        assert eval_under15_home(self.make_fixture(1, 0)) is True

    def test_under15_false(self):
        assert eval_under15_home(self.make_fixture(1, 1)) is False

    def test_under15_none(self):
        assert eval_under15_home(self.make_fixture(None, None)) is None

    def test_over45_true(self):
        assert eval_over45_home(self.make_fixture(3, 2)) is True

    def test_over45_false_exact(self):
        assert eval_over45_home(self.make_fixture(3, 1)) is False

    def test_over45_none(self):
        assert eval_over45_home(self.make_fixture(None, None)) is None

    def test_btts_over25_true(self):
        assert eval_btts_over25_home(self.make_fixture(2, 1)) is True

    def test_btts_over25_false_no_btts(self):
        """3 goals total but away didn't score."""
        assert eval_btts_over25_home(self.make_fixture(3, 0)) is False

    def test_btts_over25_false_under(self):
        """Both scored but only 2 total goals."""
        assert eval_btts_over25_home(self.make_fixture(1, 1)) is False

    def test_btts_over25_none(self):
        assert eval_btts_over25_home(self.make_fixture(None, None)) is None


class TestSession5ANonOccurrenceMarkets:
    """No Win to Nil / Not Scoring 2+ / Not Scoring 3+."""

    def make_fixture(self, ft_h=None, ft_a=None) -> dict:
        return {'ft_home': ft_h, 'ft_away': ft_a}

    def test_no_win_nil_home_true_when_not_won_to_nil(self):
        """Home won but conceded — no win-to-nil, so True."""
        assert eval_no_win_nil_home(self.make_fixture(2, 1)) is True

    def test_no_win_nil_home_false_when_won_to_nil(self):
        assert eval_no_win_nil_home(self.make_fixture(2, 0)) is False

    def test_no_win_nil_home_true_when_lost(self):
        assert eval_no_win_nil_home(self.make_fixture(0, 1)) is True

    def test_no_win_nil_away_false_when_away_won_to_nil(self):
        assert eval_no_win_nil_away(self.make_fixture(0, 2)) is False

    def test_no_win_nil_away_true_otherwise(self):
        assert eval_no_win_nil_away(self.make_fixture(1, 2)) is True

    def test_no_win_nil_none(self):
        assert eval_no_win_nil_home(self.make_fixture(None, None)) is None

    def test_no_home_2plus_true(self):
        assert eval_no_home_2plus_home(self.make_fixture(1, 0)) is True

    def test_no_home_2plus_false(self):
        assert eval_no_home_2plus_home(self.make_fixture(2, 0)) is False

    def test_no_home_2plus_edge_zero(self):
        assert eval_no_home_2plus_home(self.make_fixture(0, 0)) is True

    def test_no_away_2plus_true(self):
        assert eval_no_away_2plus_home(self.make_fixture(0, 1)) is True

    def test_no_away_2plus_false(self):
        assert eval_no_away_2plus_home(self.make_fixture(0, 2)) is False

    def test_no_home_3plus_true(self):
        assert eval_no_home_3plus_home(self.make_fixture(2, 0)) is True

    def test_no_home_3plus_false(self):
        assert eval_no_home_3plus_home(self.make_fixture(3, 0)) is False

    def test_no_away_3plus_true(self):
        assert eval_no_away_3plus_home(self.make_fixture(0, 2)) is True

    def test_no_away_3plus_false(self):
        assert eval_no_away_3plus_home(self.make_fixture(0, 3)) is False

    def test_no_home_2plus_none(self):
        assert eval_no_home_2plus_home(self.make_fixture(None, None)) is None


class TestSession5AHalfStructureMarkets:
    """Half-goal patterns, odd totals, HSH 1st half, HT 0-0, HT/FT."""

    def make_fixture(self, ft_h=None, ft_a=None, ht_h=None, ht_a=None) -> dict:
        return {'ft_home': ft_h, 'ft_away': ft_a, 'ht_home': ht_h, 'ht_away': ht_a}

    def test_no_both_halves_over05_true_goalless_half(self):
        """1H 0-0, FT 2-0 → 2nd half scored, 1st half didn't → True."""
        f = self.make_fixture(2, 0, 0, 0)
        assert eval_no_both_halves_over05_home(f) is True

    def test_no_both_halves_over05_false_both_scored(self):
        """1H 1-0, FT 2-1 → both halves scored → False."""
        f = self.make_fixture(2, 1, 1, 0)
        assert eval_no_both_halves_over05_home(f) is False

    def test_no_both_halves_over05_none(self):
        assert eval_no_both_halves_over05_home(self.make_fixture(1, 1, None, None)) is None

    def test_both_halves_under15_true(self):
        """1H 1-0, 2H 0-1 (FT 1-1) → each half has 1 goal → True."""
        f = self.make_fixture(1, 1, 1, 0)
        assert eval_both_halves_under15_home(f) is True

    def test_both_halves_under15_false(self):
        """1H 0-0, FT 2-1 → 2nd half had 3 goals → False."""
        f = self.make_fixture(2, 1, 0, 0)
        assert eval_both_halves_under15_home(f) is False

    def test_odd_total_true(self):
        assert eval_odd_total_home(self.make_fixture(2, 1)) is True

    def test_odd_total_false(self):
        assert eval_odd_total_home(self.make_fixture(2, 0)) is False

    def test_odd_total_none(self):
        assert eval_odd_total_home(self.make_fixture(None, None)) is None

    def test_hsh_1h_true(self):
        """1H 2-0, FT 2-1 → 1st half had 2, 2nd had 1 → True."""
        f = self.make_fixture(2, 1, 2, 0)
        assert eval_hsh_1h_home(f) is True

    def test_hsh_1h_false(self):
        """1H 0-0, FT 2-1 → 2nd half higher → False."""
        f = self.make_fixture(2, 1, 0, 0)
        assert eval_hsh_1h_home(f) is False

    def test_ht_00_true(self):
        assert eval_ht_00_home(self.make_fixture(2, 1, 0, 0)) is True

    def test_ht_00_false(self):
        assert eval_ht_00_home(self.make_fixture(2, 1, 1, 0)) is False

    def test_ht_00_none(self):
        assert eval_ht_00_home(self.make_fixture(2, 1, None, None)) is None

    def test_htft_hh_home_true(self):
        """Home leads at HT and wins FT."""
        f = self.make_fixture(2, 1, 1, 0)
        assert eval_htft_hh_home(f) is True

    def test_htft_hh_home_false_ht_not_leading(self):
        f = self.make_fixture(2, 1, 0, 0)
        assert eval_htft_hh_home(f) is False

    def test_htft_hh_away_true(self):
        f = self.make_fixture(1, 2, 0, 1)
        assert eval_htft_hh_away(f) is True

    def test_htft_dh_home_true(self):
        """HT draw, home wins FT."""
        f = self.make_fixture(2, 1, 1, 1)
        assert eval_htft_dh_home(f) is True

    def test_htft_dh_home_false_not_draw_at_ht(self):
        f = self.make_fixture(2, 1, 1, 0)
        assert eval_htft_dh_home(f) is False

    def test_htft_dh_away_true(self):
        f = self.make_fixture(1, 2, 1, 1)
        assert eval_htft_dh_away(f) is True

    def test_htft_none(self):
        assert eval_htft_hh_home(self.make_fixture(2, 1, None, None)) is None


class TestSession5AMultiscoreMarkets:
    """Multiscore group evaluations — exact scoreline membership checks."""

    def make_fixture(self, ft_h, ft_a) -> dict:
        return {'ft_home': ft_h, 'ft_away': ft_a}

    def test_ms_home_nil_low_true(self):
        assert eval_ms_home_nil_low_home(self.make_fixture(2, 0)) is True

    def test_ms_home_nil_low_false(self):
        assert eval_ms_home_nil_low_home(self.make_fixture(4, 0)) is False

    def test_ms_away_nil_low_true(self):
        assert eval_ms_away_nil_low_home(self.make_fixture(0, 2)) is True

    def test_ms_home_blowout_true(self):
        assert eval_ms_home_blowout_home(self.make_fixture(5, 0)) is True

    def test_ms_home_blowout_false(self):
        assert eval_ms_home_blowout_home(self.make_fixture(3, 0)) is False

    def test_ms_away_blowout_true(self):
        assert eval_ms_away_blowout_home(self.make_fixture(0, 6)) is True

    def test_ms_home_comfort_true(self):
        assert eval_ms_home_comfort_home(self.make_fixture(3, 1)) is True

    def test_ms_home_comfort_false(self):
        assert eval_ms_home_comfort_home(self.make_fixture(3, 0)) is False

    def test_ms_away_comfort_true(self):
        assert eval_ms_away_comfort_home(self.make_fixture(1, 3)) is True

    def test_ms_high_home_true(self):
        assert eval_ms_high_home_home(self.make_fixture(4, 3)) is True

    def test_ms_high_home_false(self):
        assert eval_ms_high_home_home(self.make_fixture(2, 1)) is False

    def test_ms_high_away_true(self):
        assert eval_ms_high_away_home(self.make_fixture(1, 5)) is True

    def test_ms_draw_true(self):
        assert eval_ms_draw_home(self.make_fixture(1, 1)) is True

    def test_ms_draw_false(self):
        assert eval_ms_draw_home(self.make_fixture(1, 0)) is False

    def test_ms_draw_edge_00(self):
        assert eval_ms_draw_home(self.make_fixture(0, 0)) is True

    def test_ms_none(self):
        assert eval_ms_draw_home(self.make_fixture(None, None)) is None


class TestEventBasedNoGoalMarkets:
    """no_goal_5min / no_goal_10min — event-driven evaluation path."""

    def _make_cursor(self, goal_count: int):
        cursor = MagicMock()
        cursor.fetchone.return_value = (goal_count,)
        return cursor

    def test_no_goal_true_when_zero_goals(self):
        cursor = self._make_cursor(0)
        assert evaluate_no_goal_minutes('fixture-1', 5, cursor) is True

    def test_no_goal_false_when_goal_exists(self):
        cursor = self._make_cursor(1)
        assert evaluate_no_goal_minutes('fixture-1', 5, cursor) is False

    def test_no_goal_query_includes_penalty(self):
        """Regression guard: penalties are their own event_type in
        fixture_events (distinct from 'missed_pen'), and must be counted
        alongside 'goal'/'own_goal' or scored penalties get missed."""
        cursor = self._make_cursor(0)
        evaluate_no_goal_minutes('fixture-1', 5, cursor)
        executed_sql = cursor.execute.call_args[0][0]
        assert "'penalty'" in executed_sql
        assert "'goal'" in executed_sql
        assert "'own_goal'" in executed_sql

    def test_no_goal_market_builds_streak_and_trend(self):
        cursor = MagicMock()
        # 3 fixtures: no goal early, goal early, no goal early (newest first)
        cursor.fetchone.side_effect = [(0,), (2,), (0,)]
        fixtures = [{'id': 'f1'}, {'id': 'f2'}, {'id': 'f3'}]
        streak, trend, evals = evaluate_no_goal_market(fixtures, 10, cursor)
        assert evals == [True, False, True]
        assert streak == 1  # newest (True) breaks at index 1 (False)
        assert trend == 2


class TestEvaluateTeamMarketOverride:
    """evaluate_team_market's override_evaluator param (Session 5B), used for
    CROSS_COMPLEMENTARY cross-streaks — must stay backward compatible with
    the existing 3-arg call sites (no override)."""

    def _make_fixture(self, home_id, away_id, ft_h, ft_a):
        return {'home_team_id': home_id, 'away_team_id': away_id, 'ft_home': ft_h, 'ft_away': ft_a}

    def test_no_override_uses_market_evaluate_home_away(self):
        market = CORE_MARKETS['ft_win']
        fixtures = [
            self._make_fixture('team1', 'team2', 2, 0),  # team1 home, won
            self._make_fixture('team3', 'team1', 1, 0),  # team1 away, lost
        ]
        streak, trend, evals = evaluate_team_market(fixtures, market, 'team1')
        assert evals == [True, False]

    def test_override_evaluator_bypasses_market_functions(self):
        market = CORE_MARKETS['ft_win']
        fixtures = [self._make_fixture('team1', 'team2', 0, 0)]
        # ft_win would give False/None here; override forces True regardless.
        override = lambda f: True
        streak, trend, evals = evaluate_team_market(
            fixtures, market, 'team1', override_evaluator=override
        )
        assert evals == [True]
        assert streak == 1

    def test_override_still_returns_none_for_unrelated_fixture(self):
        market = CORE_MARKETS['ft_win']
        fixtures = [self._make_fixture('other1', 'other2', 1, 0)]
        override = lambda f: True
        _, _, evals = evaluate_team_market(
            fixtures, market, 'team1', override_evaluator=override
        )
        assert evals == [None]


class TestGetTeamRecentStats:
    """get_team_recent_stats query shape — mocked cursor, no live DB."""

    def test_home_venue_filter_query_params(self):
        cursor = MagicMock()
        cursor.description = [
            ('fixture_id',), ('home_team_id',), ('away_team_id',),
            ('ft_home',), ('ft_away',), ('ht_home',), ('ht_away',),
            ('kickoff_utc',), ('home_stat',), ('away_stat',),
        ]
        cursor.fetchall.return_value = []

        get_team_recent_stats('team-uuid', 'home', 5, cursor, 'corners')

        sql, params = cursor.execute.call_args[0]
        assert params == ('team-uuid', 5)
        assert 'home_stats.corners' in sql
        assert 'away_stats.corners' in sql
        assert "f.home_team_id = %s" in sql

    def test_overall_venue_filter_uses_two_team_id_params(self):
        cursor = MagicMock()
        cursor.description = [('fixture_id',)]
        cursor.fetchall.return_value = []

        get_team_recent_stats('team-uuid', None, 5, cursor, 'yellow_cards')

        sql, params = cursor.execute.call_args[0]
        assert params == ('team-uuid', 'team-uuid', 5)
        assert 'yellow_cards' in sql

    def test_returns_dicts_with_stat_columns(self):
        cursor = MagicMock()
        cursor.description = [
            ('fixture_id',), ('home_team_id',), ('away_team_id',),
            ('ft_home',), ('ft_away',), ('ht_home',), ('ht_away',),
            ('kickoff_utc',), ('home_stat',), ('away_stat',),
        ]
        cursor.fetchall.return_value = [
            ('fx1', 'h1', 'a1', 2, 1, 1, 0, '2026-01-01', 7, 5),
        ]
        rows = get_team_recent_stats('h1', 'home', 5, cursor, 'corners')
        assert rows == [{
            'fixture_id': 'fx1', 'home_team_id': 'h1', 'away_team_id': 'a1',
            'ft_home': 2, 'ft_away': 1, 'ht_home': 1, 'ht_away': 0,
            'kickoff_utc': '2026-01-01', 'home_stat': 7, 'away_stat': 5,
        }]
