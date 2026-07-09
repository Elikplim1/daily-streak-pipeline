"""
Unit tests for Session 5B market evaluators: CROSS_COMPLEMENTARY cross-checks
and stats-based (corners/cards) evaluators, including functools.partial binding.
"""
from src.market_presets import (
    eval_cross_concedes_under_2_home, eval_cross_concedes_under_2_away,
    eval_cross_scores_under_2_home, eval_cross_scores_under_2_away,
    eval_cross_concedes_under_3_home, eval_cross_concedes_under_3_away,
    eval_cross_scores_under_3_home, eval_cross_scores_under_3_away,
    eval_cross_concedes_over_2_home, eval_cross_scores_over_2_home,
    eval_cross_concedes_over_2_away, eval_cross_scores_over_2_away,
    eval_over_corners_total, eval_under_corners_total,
    eval_over_team_stat_home, eval_over_team_stat_away,
    eval_under_team_stat_home, eval_under_team_stat_away,
    CORE_MARKETS, MatchType,
)


def make_fixture(ft_h=None, ft_a=None) -> dict:
    return {'ft_home': ft_h, 'ft_away': ft_a}


def make_stats(home_stat=None, away_stat=None) -> dict:
    return {'home_stat': home_stat, 'away_stat': away_stat}


class TestCrossConcedesFunctions:
    """Defensive perspective: goals CONCEDED by the team being evaluated."""

    def test_concedes_under_2_home_true(self):
        """Home team conceded 1 (away scored 1) -> under 2 conceded."""
        assert eval_cross_concedes_under_2_home(make_fixture(3, 1)) is True

    def test_concedes_under_2_home_false(self):
        assert eval_cross_concedes_under_2_home(make_fixture(0, 2)) is False

    def test_concedes_under_2_away_true(self):
        """Away team conceded 1 (home scored 1)."""
        assert eval_cross_concedes_under_2_away(make_fixture(1, 3)) is True

    def test_concedes_under_2_away_false(self):
        assert eval_cross_concedes_under_2_away(make_fixture(2, 0)) is False

    def test_concedes_under_3_home(self):
        assert eval_cross_concedes_under_3_home(make_fixture(1, 2)) is True
        assert eval_cross_concedes_under_3_home(make_fixture(1, 3)) is False

    def test_concedes_over_2_home(self):
        assert eval_cross_concedes_over_2_home(make_fixture(0, 2)) is True
        assert eval_cross_concedes_over_2_home(make_fixture(0, 1)) is False

    def test_concedes_over_2_away(self):
        assert eval_cross_concedes_over_2_away(make_fixture(2, 0)) is True
        assert eval_cross_concedes_over_2_away(make_fixture(1, 0)) is False

    def test_concedes_none_when_scores_missing(self):
        assert eval_cross_concedes_under_2_home(make_fixture(None, None)) is None


class TestCrossScoresFunctions:
    """Offensive perspective: goals SCORED by the team being evaluated."""

    def test_scores_under_2_home_true(self):
        assert eval_cross_scores_under_2_home(make_fixture(1, 3)) is True

    def test_scores_under_2_home_false(self):
        assert eval_cross_scores_under_2_home(make_fixture(2, 0)) is False

    def test_scores_under_2_away_true(self):
        assert eval_cross_scores_under_2_away(make_fixture(3, 1)) is True

    def test_scores_under_3_away(self):
        assert eval_cross_scores_under_3_away(make_fixture(0, 2)) is True
        assert eval_cross_scores_under_3_away(make_fixture(0, 3)) is False

    def test_scores_over_2_home(self):
        assert eval_cross_scores_over_2_home(make_fixture(2, 0)) is True
        assert eval_cross_scores_over_2_home(make_fixture(1, 0)) is False

    def test_scores_over_2_away(self):
        assert eval_cross_scores_over_2_away(make_fixture(0, 2)) is True

    def test_scores_none_when_scores_missing(self):
        assert eval_cross_scores_under_2_away(make_fixture(None, None)) is None


class TestCrossComplementaryMarketRegistration:
    """The 4 goals markets retrofitted to CROSS_COMPLEMENTARY carry cross evaluators."""

    def test_under_1_5_is_cross_complementary(self):
        market = CORE_MARKETS['under_1_5']
        assert market.match_type == MatchType.CROSS_COMPLEMENTARY
        assert market.evaluate_cross_defensive_home is eval_cross_concedes_under_2_home
        assert market.evaluate_cross_offensive_away is eval_cross_scores_under_2_away

    def test_under_2_5_is_cross_complementary(self):
        market = CORE_MARKETS['under_2_5']
        assert market.match_type == MatchType.CROSS_COMPLEMENTARY
        assert market.evaluate_cross_defensive_home is eval_cross_concedes_under_3_home
        assert market.evaluate_cross_offensive_away is eval_cross_scores_under_3_away

    def test_over_1_5_is_cross_complementary(self):
        market = CORE_MARKETS['over_1_5']
        assert market.match_type == MatchType.CROSS_COMPLEMENTARY

    def test_over_2_5_is_cross_complementary(self):
        market = CORE_MARKETS['over_2_5']
        assert market.match_type == MatchType.CROSS_COMPLEMENTARY

    def test_other_goal_markets_unaffected(self):
        """Markets not explicitly retrofitted keep their original match_type."""
        assert CORE_MARKETS['under_3_5'].match_type == MatchType.COMBINED
        assert CORE_MARKETS['over_4_5'].match_type == MatchType.COMBINED


class TestCornerCardEvaluators:
    """Stats-based evaluators — verify the fixed Under boundary specifically."""

    def test_over_corners_total_true(self):
        assert eval_over_corners_total(make_stats(5, 4), threshold=8.5) is True

    def test_over_corners_total_false(self):
        assert eval_over_corners_total(make_stats(4, 4), threshold=8.5) is False

    def test_under_corners_total_excludes_line_plus_half(self):
        """Regression guard for the off-by-one bug: Under 8.5 must exclude a
        total of 9 (the spec's own code computed `< threshold + 1` = `< 9.5`,
        which incorrectly let 9 through)."""
        assert eval_under_corners_total(make_stats(5, 4), threshold=8.5) is False  # total=9

    def test_under_corners_total_includes_line_minus_half(self):
        assert eval_under_corners_total(make_stats(4, 4), threshold=8.5) is True  # total=8

    def test_corners_total_none_when_missing(self):
        assert eval_over_corners_total(make_stats(None, 4), threshold=8.5) is None
        assert eval_under_corners_total(make_stats(5, None), threshold=8.5) is None

    def test_over_team_stat_home(self):
        assert eval_over_team_stat_home(make_stats(4, 3), threshold=3.5) is True
        assert eval_over_team_stat_home(make_stats(3, 3), threshold=3.5) is False

    def test_over_team_stat_away(self):
        assert eval_over_team_stat_away(make_stats(3, 4), threshold=3.5) is True

    def test_under_team_stat_home_excludes_line_plus_half(self):
        """Under 3.5 must exclude 4 (same off-by-one class of bug)."""
        assert eval_under_team_stat_home(make_stats(4, 0), threshold=3.5) is False

    def test_under_team_stat_home_includes_line_minus_half(self):
        assert eval_under_team_stat_home(make_stats(3, 0), threshold=3.5) is True

    def test_under_team_stat_away(self):
        assert eval_under_team_stat_away(make_stats(0, 1), threshold=1.5) is True
        assert eval_under_team_stat_away(make_stats(0, 2), threshold=1.5) is False

    def test_team_stat_none_when_missing(self):
        assert eval_over_team_stat_home(make_stats(None, 3), threshold=3.5) is None
        assert eval_under_team_stat_away(make_stats(3, None), threshold=1.5) is None


class TestFunctoolsPartialBinding:
    """functools.partial-bound evaluators, as used in market registration."""

    def test_partial_binds_threshold_correctly(self):
        from functools import partial
        over_85 = partial(eval_over_corners_total, threshold=8.5)
        over_95 = partial(eval_over_corners_total, threshold=9.5)
        f = make_stats(5, 4)  # total = 9
        assert over_85(f) is True
        assert over_95(f) is False

    def test_registered_market_evaluators_are_callable_partials(self):
        market = CORE_MARKETS['over_8_5_corners']
        assert market.stats_based is True
        assert market.stats_column == 'corners'
        # Should behave identically to the unbound function with threshold=8.5
        assert market.evaluate_home(make_stats(5, 4)) is True
        assert market.evaluate_away(make_stats(4, 4)) is False

    def test_under_market_uses_fixed_boundary(self):
        market = CORE_MARKETS['under_8_5_corners']
        assert market.evaluate_home(make_stats(5, 4)) is False  # total=9, must be excluded


class TestStatsMarketRegistration:
    def test_all_20_stats_markets_registered(self):
        expected_keys = [
            "over_8_5_corners", "under_8_5_corners",
            "over_9_5_corners", "under_9_5_corners",
            "over_10_5_corners", "under_10_5_corners",
            "over_11_5_corners", "under_11_5_corners",
            "over_3_5_team_corners", "under_3_5_team_corners",
            "over_4_5_team_corners", "under_4_5_team_corners",
            "over_5_5_team_corners", "under_5_5_team_corners",
            "over_2_5_cards", "under_2_5_cards",
            "over_3_5_cards", "under_3_5_cards",
            "over_1_5_team_cards", "under_1_5_team_cards",
        ]
        assert len(expected_keys) == 20
        for key in expected_keys:
            assert key in CORE_MARKETS, f"{key} not registered"
            assert CORE_MARKETS[key].stats_based is True

    def test_stats_markets_use_combined_not_cross_complementary(self):
        """No real cross evaluators exist for corners/cards, so they should
        NOT be labeled CROSS_COMPLEMENTARY (that would be misleading)."""
        for key in ["over_8_5_corners", "over_3_5_team_corners", "over_2_5_cards", "over_1_5_team_cards"]:
            assert CORE_MARKETS[key].match_type == MatchType.COMBINED
            assert CORE_MARKETS[key].evaluate_cross_defensive_home is None
