"""
Unit tests for the correlation checker — signal tier classification,
including per-market threshold overrides.
"""
from src.correlation_checker import classify_signal_tier
from src.streak_scanner import StreakResult


def make_streak(streak_length: int, trend_count: int = None) -> StreakResult:
    return StreakResult(
        market_key='test', team_id='t1', venue_lens='overall',
        streak_length=streak_length,
        trend_count=trend_count if trend_count is not None else streak_length,
        window_size=5,
    )


class TestDefaultThresholds:
    """Markets with no override use the global HIGH_SIGNAL_MIN/MODERATE_SIGNAL_MIN (5/4)."""

    def test_high_signal_on_perfect_streak_with_alignment(self):
        tier = classify_signal_tier(
            make_streak(5), make_streak(5), make_streak(5), make_streak(5),
            alignment_met=True, market_key='ft_win',
        )
        assert tier == 'HIGH_SIGNAL'

    def test_moderate_signal_on_four_of_five(self):
        tier = classify_signal_tier(
            make_streak(4), make_streak(4), make_streak(2), make_streak(2),
            alignment_met=False, market_key='ft_win',
        )
        assert tier == 'MODERATE_SIGNAL'

    def test_tracking_below_moderate(self):
        tier = classify_signal_tier(
            make_streak(3), make_streak(3), make_streak(2), make_streak(2),
            alignment_met=False, market_key='ft_win',
        )
        assert tier == 'TRACKING'

    def test_no_market_key_falls_back_to_default(self):
        tier = classify_signal_tier(
            make_streak(4), make_streak(4), make_streak(2), make_streak(2),
            alignment_met=False,
        )
        assert tier == 'MODERATE_SIGNAL'


class TestMarketThresholdOverrides:
    """Overridden markets (config.MARKET_THRESHOLD_OVERRIDES) require a
    perfect 5/5 streak to register as MODERATE or HIGH — a 4/5 streak,
    which is enough for MODERATE on any other market, stays TRACKING."""

    def test_four_of_five_stays_tracking_for_overridden_market(self):
        tier = classify_signal_tier(
            make_streak(4), make_streak(4), make_streak(2), make_streak(2),
            alignment_met=False, market_key='no_goal_5min',
        )
        assert tier == 'TRACKING'

    def test_perfect_streak_with_alignment_is_high_signal(self):
        tier = classify_signal_tier(
            make_streak(5), make_streak(5), make_streak(5), make_streak(5),
            alignment_met=True, market_key='no_goal_5min',
        )
        assert tier == 'HIGH_SIGNAL'

    def test_perfect_streak_without_alignment_is_moderate(self):
        tier = classify_signal_tier(
            make_streak(5), make_streak(5), make_streak(1), make_streak(1),
            alignment_met=False, market_key='no_win_nil_home',
        )
        assert tier == 'MODERATE_SIGNAL'

    def test_applies_to_all_eight_overridden_markets(self):
        overridden_markets = [
            'no_goal_5min', 'no_goal_10min',
            'no_home_3plus', 'no_away_3plus',
            'no_win_nil_home', 'no_win_nil_away',
            'no_home_2plus', 'no_away_2plus',
        ]
        for mkey in overridden_markets:
            tier = classify_signal_tier(
                make_streak(4), make_streak(4), make_streak(2), make_streak(2),
                alignment_met=False, market_key=mkey,
            )
            assert tier == 'TRACKING', f"{mkey} should stay TRACKING on a 4/5 streak"
