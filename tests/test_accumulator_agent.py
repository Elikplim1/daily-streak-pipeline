"""
Unit tests for accumulator_agent.py — evidence scoring, diversification
constraints, league validation, BTTS HIGH_SIGNAL-only filtering, and
Telegram message formatting.
"""
from unittest.mock import MagicMock

from src.accumulator_agent import (
    AccumulatorCandidate,
    BttsReferenceCard,
    calculate_evidence_score,
    is_validated_league,
    fetch_candidates,
    select_best_5,
    format_accumulator_message,
    team_recent_scored_count,
    fetch_btts_signal_fixtures,
    build_btts_live_reference,
    format_btts_reference_message,
    build_btts_reference_report,
    LOCKED_MARKETS,
    MAX_SELECTIONS,
    MAX_PER_LEAGUE,
    MIN_TEAM_SCORE_STREAK_FOR_REFERENCE,
    TEAM_SCORE_LOOKBACK,
    BTTS_AWAY_FIRST_RESPONSE,
)


def make_candidate(**overrides) -> AccumulatorCandidate:
    defaults = dict(
        fixture_id='fx-1', fixture_date='2026-07-16T15:00:00+00:00',
        league_name='Premier League', home_team='Home FC', away_team='Away FC',
        market_key='dc_1x_ft', market_name='DC 1X (FT)',
        signal_tier='HIGH_SIGNAL', alignment_met=True,
        home_venue_streak=5, home_overall_streak=5,
        away_venue_streak=3, away_overall_streak=4,
    )
    defaults.update(overrides)
    return AccumulatorCandidate(**defaults)


class TestEvidenceScore:
    def test_known_inputs_full_streak_aligned_high_signal(self):
        """Max streak 5/5, aligned, HIGH_SIGNAL, dc_1x_ft (72.8% acc, weight 1.0):
        40 (streak) + 15 (alignment) + 15 (league) + 15 (signal tier)
        + (72.8-50)/50*15*1.0 = 6.84 (market) = 91.84 -> 91.8
        """
        c = make_candidate()
        score = calculate_evidence_score(c)
        assert score == 91.84 or round(score, 1) == 91.8
        assert c.evidence_score == 91.8

    def test_unaligned_scores_lower_than_aligned(self):
        aligned = make_candidate(alignment_met=True)
        unaligned = make_candidate(alignment_met=False)
        calculate_evidence_score(aligned)
        calculate_evidence_score(unaligned)
        assert aligned.evidence_score - unaligned.evidence_score == 15

    def test_moderate_signal_scores_lower_than_high(self):
        high = make_candidate(signal_tier='HIGH_SIGNAL')
        moderate = make_candidate(signal_tier='MODERATE_SIGNAL')
        calculate_evidence_score(high)
        calculate_evidence_score(moderate)
        assert high.evidence_score - moderate.evidence_score == 7

    def test_streak_score_capped_at_40(self):
        """Streak values above STREAK_WINDOW (5) shouldn't push the streak
        component past its 40-point cap."""
        c = make_candidate(home_venue_streak=99, home_overall_streak=99,
                            away_venue_streak=0, away_overall_streak=0,
                            alignment_met=False, signal_tier='MODERATE_SIGNAL')
        calculate_evidence_score(c)
        # 40 (streak, capped) + 0 (alignment) + 15 (league) + 8 (moderate) + market
        market_component = (LOCKED_MARKETS['dc_1x_ft']['accuracy'] - 50) / 50 * 15 * \
            LOCKED_MARKETS['dc_1x_ft']['weight']
        expected = round(40 + 15 + 8 + market_component, 1)
        assert c.evidence_score == expected

    def test_reasons_populated(self):
        c = make_candidate()
        calculate_evidence_score(c)
        assert len(c.reasons) >= 5
        assert any('streak' in r.lower() for r in c.reasons)


class TestLeagueValidation:
    def test_backtested_league_is_validated(self):
        assert is_validated_league('Premier League') is True
        assert is_validated_league('Serie A') is True

    def test_untested_league_is_not_validated(self):
        """Leagues with no 2024 fixture history in this DB must not be
        treated as validated, even if a draft spec once labeled one
        'TIER_1 — confirmed strong home advantage'."""
        assert is_validated_league('Iceland Urvalsdeild') is False
        assert is_validated_league('MLS') is False

    def test_unknown_league_is_not_validated(self):
        assert is_validated_league('Not A Real League') is False


class TestSelectBest5:
    def test_ranks_by_evidence_score_descending(self):
        low = make_candidate(fixture_id='fx-1', league_name='Serie A',
                              home_venue_streak=3, away_venue_streak=3, alignment_met=False)
        high = make_candidate(fixture_id='fx-2', league_name='La Liga')
        calculate_evidence_score(low)
        calculate_evidence_score(high)
        selected = select_best_5([low, high])
        assert selected[0] is high

    def test_max_one_per_fixture(self):
        a = make_candidate(fixture_id='fx-1', market_key='dc_1x_ft', league_name='Serie A')
        b = make_candidate(fixture_id='fx-1', market_key='under_3_5', league_name='Serie A')
        for c in (a, b):
            calculate_evidence_score(c)
        selected = select_best_5([a, b])
        assert len(selected) == 1

    def test_max_per_league_enforced(self):
        candidates = [
            make_candidate(fixture_id=f'fx-{i}', league_name='Serie A')
            for i in range(4)
        ]
        for c in candidates:
            calculate_evidence_score(c)
        selected = select_best_5(candidates)
        assert len(selected) == MAX_PER_LEAGUE

    def test_caps_at_max_selections(self):
        leagues = ['Serie A', 'La Liga', 'Ligue 1', 'Bundesliga', 'Premier League',
                   'Championship', 'Serie B']
        candidates = [
            make_candidate(fixture_id=f'fx-{i}', league_name=leagues[i % len(leagues)])
            for i in range(10)
        ]
        for c in candidates:
            calculate_evidence_score(c)
        selected = select_best_5(candidates)
        assert len(selected) <= MAX_SELECTIONS

    def test_empty_input_returns_empty(self):
        assert select_best_5([]) == []


class TestFetchCandidatesFiltering:
    def _cursor_with_rows(self, rows):
        cursor = MagicMock()
        cols = [
            'fixture_id', 'fixture_date', 'league_name',
            'home_team_name', 'away_team_name',
            'market_key', 'market_name', 'signal_tier', 'alignment_met',
            'home_venue_streak', 'home_overall_streak',
            'away_venue_streak', 'away_overall_streak',
        ]
        cursor.description = [(c,) for c in cols]
        cursor.fetchall.return_value = rows
        return cursor

    def test_btts_moderate_signal_excluded(self):
        """gg_ft is high_only in LOCKED_MARKETS — a MODERATE_SIGNAL BTTS
        row must never become a candidate."""
        row = (
            'fx-1', '2026-07-16T15:00:00+00:00', 'Premier League',
            'Home FC', 'Away FC', 'gg_ft', 'BTTS Yes', 'MODERATE_SIGNAL', True,
            5, 5, 5, 5,
        )
        cursor = self._cursor_with_rows([row])
        candidates = fetch_candidates(cursor)
        assert candidates == []

    def test_btts_high_signal_included(self):
        row = (
            'fx-1', '2026-07-16T15:00:00+00:00', 'Premier League',
            'Home FC', 'Away FC', 'gg_ft', 'BTTS Yes', 'HIGH_SIGNAL', True,
            5, 5, 5, 5,
        )
        cursor = self._cursor_with_rows([row])
        candidates = fetch_candidates(cursor)
        assert len(candidates) == 1
        assert candidates[0].market_key == 'gg_ft'

    def test_untested_league_excluded(self):
        row = (
            'fx-1', '2026-07-16T15:00:00+00:00', 'Iceland Urvalsdeild',
            'Home FC', 'Away FC', 'dc_1x_ft', 'DC 1X (FT)', 'HIGH_SIGNAL', True,
            5, 5, 5, 5,
        )
        cursor = self._cursor_with_rows([row])
        assert fetch_candidates(cursor) == []

    def test_below_min_evidence_score_excluded(self):
        """Weak, unaligned MODERATE signal shouldn't clear MIN_EVIDENCE_SCORE (60)."""
        row = (
            'fx-1', '2026-07-16T15:00:00+00:00', 'Premier League',
            'Home FC', 'Away FC', 'dc_1x_ft', 'DC 1X (FT)', 'MODERATE_SIGNAL', False,
            1, 0, 0, 0,
        )
        cursor = self._cursor_with_rows([row])
        assert fetch_candidates(cursor) == []


class TestMessageFormatting:
    def test_empty_selections_shows_restraint_message(self):
        msg = format_accumulator_message([])
        assert 'No Selections Today' in msg
        assert 'restraint' in msg.lower()

    def test_populated_selections_includes_reasoning(self):
        c = make_candidate()
        calculate_evidence_score(c)
        msg = format_accumulator_message([c])
        assert 'Home FC vs Away FC' in msg
        assert 'Evidence Score' in msg
        assert 'Why this selection' in msg
        for reason in c.reasons:
            assert reason in msg

    def test_selection_count_reflects_actual_list(self):
        c = make_candidate()
        calculate_evidence_score(c)
        msg = format_accumulator_message([c])
        assert f"Selections: 1/{MAX_SELECTIONS}" in msg


def make_btts_row(**overrides):
    """Row shape matching fetch_btts_signal_fixtures's SELECT column order."""
    defaults = dict(
        fixture_id='fx-1', fixture_date='2026-07-18T02:45:00+00:00',
        league_name='Premier League',
        home_team_id='team-h1', home_team_name='Home FC',
        away_team_id='team-a1', away_team_name='Away FC',
        signal_tier='HIGH_SIGNAL',
        home_venue_streak=5, home_overall_streak=4,
        away_venue_streak=4, away_overall_streak=3,
    )
    defaults.update(overrides)
    cols = list(defaults.keys())
    return cols, tuple(defaults[c] for c in cols)


def make_btts_card(**overrides) -> BttsReferenceCard:
    defaults = dict(
        fixture_id='fx-1', fixture_date='2026-07-18T02:45:00+00:00',
        league_name='Premier League', home_team='Home FC', away_team='Away FC',
        signal_tier='HIGH_SIGNAL',
        home_scored=5, home_played=5, away_scored=4, away_played=5,
        btts_streak=4, btts_window=TEAM_SCORE_LOOKBACK,
    )
    defaults.update(overrides)
    return BttsReferenceCard(**defaults)


class TestTeamRecentScoredCount:
    def test_counts_scored_matches_home(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(True,), (True,), (False,), (True,), (True,)]
        scored, played = team_recent_scored_count(cursor, 'team-1', 'home')
        assert scored == 4
        assert played == 5

    def test_short_history_returns_fewer_played(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(True,), (False,)]
        scored, played = team_recent_scored_count(cursor, 'team-1', 'away')
        assert scored == 1
        assert played == 2

    def test_home_query_uses_home_columns(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        team_recent_scored_count(cursor, 'team-1', 'home')
        executed_sql = cursor.execute.call_args[0][0]
        assert 'ft_home' in executed_sql
        assert 'home_team_id' in executed_sql

    def test_away_query_uses_away_columns(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        team_recent_scored_count(cursor, 'team-1', 'away')
        executed_sql = cursor.execute.call_args[0][0]
        assert 'ft_away' in executed_sql
        assert 'away_team_id' in executed_sql

    def test_lookback_matches_team_score_lookback_constant(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        team_recent_scored_count(cursor, 'team-1', 'home')
        params = cursor.execute.call_args[0][1]
        assert params[-1] == TEAM_SCORE_LOOKBACK


class TestFetchBttsSignalFixtures:
    def test_query_filters_to_gg_ft_and_signal_tiers(self):
        cols, row = make_btts_row()
        cursor = MagicMock()
        cursor.description = [(c,) for c in cols]
        cursor.fetchall.return_value = [row]
        rows = fetch_btts_signal_fixtures(cursor)
        assert len(rows) == 1
        executed_sql = cursor.execute.call_args[0][0]
        assert "gg_ft" in executed_sql
        assert "HIGH_SIGNAL" in executed_sql and "MODERATE_SIGNAL" in executed_sql


class TestBuildBttsLiveReference:
    def _cursor_for(self, fixture_rows, score_sequences):
        """fixture_rows: list of (cols, row) from make_btts_row().
        score_sequences: fetchall return values for each subsequent
        team_recent_scored_count call, in call order (home, then away,
        per fixture)."""
        cursor = MagicMock()
        cols = fixture_rows[0][0] if fixture_rows else [
            'fixture_id', 'fixture_date', 'league_name',
            'home_team_id', 'home_team_name', 'away_team_id', 'away_team_name',
            'signal_tier', 'home_venue_streak', 'home_overall_streak',
            'away_venue_streak', 'away_overall_streak',
        ]
        cursor.description = [(c,) for c in cols]
        rows = [r for _, r in fixture_rows]
        cursor.fetchall.side_effect = [rows] + score_sequences
        return cursor

    def test_qualifying_fixture_produces_card(self):
        row = make_btts_row()
        cursor = self._cursor_for(
            [row],
            [
                [(True,)] * 5,                  # home: 5/5 scored
                [(True,)] * 4 + [(False,)],      # away: 4/5 scored
            ],
        )
        cards = build_btts_live_reference(cursor)
        assert len(cards) == 1
        card = cards[0]
        assert card.home_scored == 5 and card.home_played == 5
        assert card.away_scored == 4 and card.away_played == 5
        assert card.btts_streak == min(max(5, 4), max(4, 3))  # min(5,4) = 4

    def test_home_below_threshold_excluded(self):
        row = make_btts_row()
        cursor = self._cursor_for(
            [row],
            [
                [(True,)] * 3 + [(False,)] * 2,   # home: 3/5 — below the 4/5 bar
                [(True,)] * 5,
            ],
        )
        assert build_btts_live_reference(cursor) == []

    def test_away_below_threshold_excluded(self):
        row = make_btts_row()
        cursor = self._cursor_for(
            [row],
            [
                [(True,)] * 5,
                [(True,)] * 2 + [(False,)] * 3,   # away: 2/5
            ],
        )
        assert build_btts_live_reference(cursor) == []

    def test_no_signal_fixtures_returns_empty(self):
        cursor = self._cursor_for([], [])
        assert build_btts_live_reference(cursor) == []

    def test_min_threshold_is_moderate_signal_min(self):
        assert MIN_TEAM_SCORE_STREAK_FOR_REFERENCE == 4


class TestFormatBttsReferenceMessage:
    def test_empty_cards_shows_no_fixtures_message(self):
        msg = format_btts_reference_message([])
        assert 'No Qualifying Fixtures Today' in msg

    def test_known_league_shows_real_response_rate(self):
        card = make_btts_card(league_name='Premier League')
        msg = format_btts_reference_message([card])
        rate, n = BTTS_AWAY_FIRST_RESPONSE['Premier League']
        assert f"{rate}%" in msg
        assert f"{n} samples" in msg

    def test_unknown_league_does_not_fabricate_rate(self):
        assert 'MLS' not in BTTS_AWAY_FIRST_RESPONSE
        card = make_btts_card(league_name='MLS')
        msg = format_btts_reference_message([card])
        assert 'no backtested response rate' in msg.lower()

    def test_reverse_direction_never_claims_a_rate(self):
        card = make_btts_card()
        msg = format_btts_reference_message([card])
        assert 'never been backtested' in msg.lower()

    def test_includes_fixture_and_scoring_form(self):
        card = make_btts_card()
        msg = format_btts_reference_message([card])
        assert 'Home FC vs Away FC' in msg
        assert '5/5' in msg
        assert '4/5' in msg


class TestBuildBttsReferenceReport:
    def test_empty_cards_returns_none(self):
        assert build_btts_reference_report([]) is None
