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


class TestSupportingEvidenceOnly:
    """Markets in config.SUPPORTING_EVIDENCE_ONLY never fire independently —
    always TRACKING regardless of streak values or alignment. This check
    runs before MARKET_THRESHOLD_OVERRIDES is even consulted, so it wins
    even though every SUPPORTING_EVIDENCE_ONLY market also happens to have
    a (now unreachable) entry in MARKET_THRESHOLD_OVERRIDES."""

    def test_perfect_streak_with_alignment_still_tracking(self):
        """Even a 5/5 streak with alignment met — the strongest possible
        signal — stays TRACKING for a supporting-evidence market."""
        tier = classify_signal_tier(
            make_streak(5), make_streak(5), make_streak(5), make_streak(5),
            alignment_met=True, market_key='no_goal_5min',
        )
        assert tier == 'TRACKING'

    def test_four_of_five_stays_tracking(self):
        tier = classify_signal_tier(
            make_streak(4), make_streak(4), make_streak(2), make_streak(2),
            alignment_met=False, market_key='no_win_nil_home',
        )
        assert tier == 'TRACKING'

    def test_applies_to_all_eight_supporting_markets(self):
        supporting_markets = [
            'no_goal_5min', 'no_goal_10min',
            'no_home_3plus', 'no_away_3plus',
            'no_win_nil_home', 'no_win_nil_away',
            'no_home_2plus', 'no_away_2plus',
        ]
        for mkey in supporting_markets:
            tier = classify_signal_tier(
                make_streak(5), make_streak(5), make_streak(5), make_streak(5),
                alignment_met=True, market_key=mkey,
            )
            assert tier == 'TRACKING', f"{mkey} should always be TRACKING, even on 5/5 with alignment"

    def test_non_supporting_market_unaffected(self):
        """Sanity check: a market NOT in SUPPORTING_EVIDENCE_ONLY still
        fires normally on a perfect aligned streak."""
        tier = classify_signal_tier(
            make_streak(5), make_streak(5), make_streak(5), make_streak(5),
            alignment_met=True, market_key='ft_win',
        )
        assert tier == 'HIGH_SIGNAL'
