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
from typing import List, Optional, Tuple

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

    Args:
        high_signals: List of (FixtureScanResult, market_key, market_data) tuples
        pipeline_run_id: Run ID for traceability
        total_fixtures: Total fixtures scanned in this run

    Returns:
        Formatted MarkdownV2 string, or None if high_signals is empty.
    """
    if not high_signals:
        return None

    lines = [
        "🔴 *STREAK ALERT — HIGH SIGNAL* 🔴",
        "",
        escape_markdown_v2(f"Fixtures scanned: {total_fixtures}"),
        escape_markdown_v2(f"High signals: {len(high_signals)}"),
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    for fr, mkey, mdata in high_signals:
        market = CORE_MARKETS[mkey]
        hv = mdata['home_venue']
        ho = mdata['home_overall']
        av = mdata['away_venue']
        ao = mdata['away_overall']

        home_name = escape_markdown_v2(fr.home_team_name)
        away_name = escape_markdown_v2(fr.away_team_name)
        market_name = escape_markdown_v2(market.name)
        date_str = escape_markdown_v2(
            fr.fixture_date[:10] if fr.fixture_date else 'TBD'
        )

        lines += [
            "",
            f"⚽ *{home_name} vs {away_name}*",
            f"📊 Market: {market_name}",
            (
                f"🏠 Home: {hv.streak_length}v/{ho.streak_length}o "
                f"\\(trend {hv.trend_count}/{ho.trend_count}\\)"
            ),
            (
                f"✈️ Away: {av.streak_length}v/{ao.streak_length}o "
                f"\\(trend {av.trend_count}/{ao.trend_count}\\)"
            ),
            f"✅ Alignment: {escape_markdown_v2(market.match_type)}",
            f"📅 {date_str}",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]

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
