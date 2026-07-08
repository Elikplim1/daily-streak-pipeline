"""
Telegram Bot Notifier for daily-streak-pipeline.

Formats flagged opportunities into readable Telegram messages and sends them
via the Telegram Bot API. Respects SHADOW_MODE — when True, formats the message
but logs it instead of sending detailed alerts (summary is always sent).

Message format uses Telegram MarkdownV2 for rich formatting with a plain-text
fallback if the API rejects the formatted message.
"""
import logging
import time
from typing import Dict, List, Optional, Tuple

import requests

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SHADOW_MODE
from src.market_presets import CORE_MARKETS

logger = logging.getLogger(__name__)

_TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

TIER_EMOJI = {
    'HIGH_SIGNAL': '🔴',
    'MODERATE_SIGNAL': '🟡',
    'TRACKING': '⚪',
}


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    result = ''
    for char in str(text):
        if char in special_chars:
            result += f'\\{char}'
        else:
            result += char
    return result


def build_high_signal_message(
    high_signals: List[Tuple],
    pipeline_run_id: str,
    total_fixtures: int,
) -> Optional[str]:
    """
    Build the MarkdownV2 Telegram message for HIGH_SIGNAL opportunities.

    Groups all HIGH_SIGNAL markets under each fixture (one block per fixture,
    all its markets listed together) instead of one block per market.

    Args:
        high_signals: List of (FixtureScanResult, market_key, market_data) tuples
        pipeline_run_id: Run ID for traceability
        total_fixtures: Total fixtures scanned in this run

    Returns:
        Formatted MarkdownV2 string, or None if high_signals is empty.
    """
    if not high_signals:
        return None

    # Group by fixture, preserving each fixture's markets in encounter order.
    fixtures_by_id: Dict[str, dict] = {}
    for fr, mkey, mdata in high_signals:
        entry = fixtures_by_id.setdefault(fr.fixture_id, {'fr': fr, 'markets': []})
        entry['markets'].append((mkey, mdata))

    ordered_fixture_ids = sorted(
        fixtures_by_id, key=lambda fid: fixtures_by_id[fid]['fr'].fixture_date or ''
    )

    lines = [
        (
            f"🔴 *HIGH SIGNAL — {len(ordered_fixture_ids)} fixtures, "
            f"{len(high_signals)} markets*"
        ),
        "",
        escape_markdown_v2(f"Fixtures scanned: {total_fixtures}"),
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    for fid in ordered_fixture_ids:
        fr = fixtures_by_id[fid]['fr']
        markets = fixtures_by_id[fid]['markets']

        home_name = escape_markdown_v2(fr.home_team_name)
        away_name = escape_markdown_v2(fr.away_team_name)
        league_name = escape_markdown_v2(fr.league_name)
        fixture_date = fr.fixture_date or ''
        date_str = escape_markdown_v2(fixture_date[:10] if fixture_date else 'TBD')
        time_str = escape_markdown_v2(
            fixture_date[11:16] if len(fixture_date) > 11 else '??:??'
        )

        lines += [
            "",
            f"⚽ *{home_name} vs {away_name}*",
            f"📅 {date_str}, {time_str} UTC \\| {league_name}",
        ]

        for mkey, mdata in markets:
            market = CORE_MARKETS[mkey]
            hv = mdata['home_venue']
            ho = mdata['home_overall']
            av = mdata['away_venue']
            ao = mdata['away_overall']

            market_name = escape_markdown_v2(market.name)
            match_type = escape_markdown_v2(market.match_type)

            lines += [
                "",
                f"  📊 {market_name} \\({match_type}\\)",
                (
                    f"  🏠 Home: {hv.streak_length}v/{ho.streak_length}o "
                    f"\\(Venue\\) \\| {hv.trend_count}/{ho.trend_count} \\(Overall\\)"
                ),
                (
                    f"  ✈️ Away: {av.streak_length}v/{ao.streak_length}o "
                    f"\\(Venue\\) \\| {av.trend_count}/{ao.trend_count} \\(Overall\\)"
                ),
            ]

        lines.append("━━━━━━━━━━━━━━━━━━━━━")

    lines += [
        "",
        f"_Run: {escape_markdown_v2(pipeline_run_id)}_",
        "_Shadow mode: OFF — LIVE ALERTS_",
    ]

    return "\n".join(lines)


def build_summary_message(
    total_fixtures: int,
    high_count: int,
    moderate_count: int,
    tracking_count: int,
    rows_written: int,
    pipeline_run_id: str,
) -> str:
    """
    Build the daily summary message in plain text.

    Always sent, even in shadow mode — gives Eli a daily confirmation the
    pipeline ran successfully.
    """
    lines = [
        "📊 STREAK PIPELINE — Daily Summary",
        "",
        f"Fixtures scanned: {total_fixtures}",
        f"🔴 HIGH_SIGNAL:    {high_count}",
        f"🟡 MODERATE_SIGNAL:{moderate_count}",
        f"⚪ TRACKING:       {tracking_count}",
        f"Rows written:      {rows_written}",
        "",
    ]
    if high_count == 0:
        lines.append("No high-confidence opportunities today.")
    if SHADOW_MODE:
        lines.append("(Shadow mode ON — alert details logged, not broadcast)")
    lines.append(f"Run: {pipeline_run_id}")
    return "\n".join(lines)


def send_telegram_message(
    text: str,
    parse_mode: Optional[str] = None,
) -> bool:
    """
    Send a message via Telegram Bot API.

    Args:
        text:       Message text
        parse_mode: 'MarkdownV2', 'HTML', or None for plain text

    Returns:
        True if delivered successfully, False otherwise.

    If a MarkdownV2 message is rejected (e.g. escaping edge-case), retries
    automatically as plain text before returning False.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials not configured — cannot send message")
        return False

    payload: dict = {'chat_id': TELEGRAM_CHAT_ID, 'text': text}
    if parse_mode:
        payload['parse_mode'] = parse_mode

    try:
        response = requests.post(
            f"{_TELEGRAM_API}/sendMessage",
            json=payload,
            timeout=30,
        )

        if response.status_code == 200:
            logger.info("Telegram message sent successfully")
            return True

        logger.error(
            f"Telegram API error {response.status_code}: {response.text[:200]}"
        )
        if parse_mode == 'MarkdownV2':
            logger.info("Retrying without MarkdownV2 formatting...")
            return send_telegram_message(text, parse_mode=None)
        return False

    except requests.exceptions.Timeout:
        logger.error("Telegram API request timed out")
        return False
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Telegram connection error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram message: {e}")
        return False


def send_alerts(
    high_signals: List[Tuple],
    total_fixtures: int,
    high_count: int,
    moderate_count: int,
    tracking_count: int,
    rows_written: int,
    pipeline_run_id: str,
) -> None:
    """
    Main entry point: send Telegram alerts based on SHADOW_MODE.

    Shadow mode (SHADOW_MODE=true):
      - Sends the daily summary message (always useful)
      - Logs what HIGH_SIGNAL alerts would have been sent (does not call API)

    Live mode (SHADOW_MODE=false):
      - Sends the daily summary
      - Sends detailed HIGH_SIGNAL alert with streak breakdowns
    """
    summary = build_summary_message(
        total_fixtures, high_count, moderate_count,
        tracking_count, rows_written, pipeline_run_id,
    )

    if SHADOW_MODE:
        logger.info("SHADOW MODE — sending summary only")
        send_telegram_message(summary)

        if high_signals:
            alert_msg = build_high_signal_message(
                high_signals, pipeline_run_id, total_fixtures
            )
            if alert_msg:
                logger.info(f"SHADOW: Would have sent alert:\n{alert_msg}")

    else:
        logger.info("LIVE MODE — sending summary + HIGH_SIGNAL alerts")
        send_telegram_message(summary)

        if high_signals:
            time.sleep(1)  # Respect Telegram rate limit (30 msg/s)
            alert_msg = build_high_signal_message(
                high_signals, pipeline_run_id, total_fixtures
            )
            if alert_msg:
                send_telegram_message(alert_msg, parse_mode='MarkdownV2')

    logger.info(
        f"Telegram notify complete: shadow={SHADOW_MODE}, "
        f"high_signals={len(high_signals)}"
    )
