#!/usr/bin/env python3
"""
SpaceX IPO Notification Bot

Monitors online sources every 5 minutes for news about SpaceX going public.
Sends SMS alerts via Twilio for both confirmed IPO events and rumored dates.
Also checks watched tickers 10 seconds after each weekday's NYSE/NASDAQ
opening bell (9:30:10 AM ET) to catch the moment trading begins.

Usage:
    python spacex_ipo_bot.py          # Run with Twilio (default)
    python spacex_ipo_bot.py --test   # Run once with console output (no SMS)
"""

import json
import time
import logging
import argparse
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set
from zoneinfo import ZoneInfo

import config
from sources import check_all_sources, check_ticker_live, Article
from notifier import create_notifier, BaseNotifier

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("spacex_ipo_bot")

# =============================================================================
# DEDUPLICATION
# =============================================================================


def load_seen_articles() -> Set[str]:
    """Load previously seen article URLs from disk."""
    path = Path(config.SEEN_ARTICLES_FILE)
    if path.exists():
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return set(data.get("urls", []))
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load seen articles file: {e}")
    return set()


def save_seen_articles(seen: Set[str]) -> None:
    """Save seen article URLs to disk."""
    path = Path(config.SEEN_ARTICLES_FILE)
    try:
        with open(path, "w") as f:
            json.dump({"urls": list(seen), "last_updated": datetime.utcnow().isoformat()}, f, indent=2)
    except IOError as e:
        logger.error(f"Could not save seen articles file: {e}")


# =============================================================================
# RATE LIMITING FOR RUMORS
# =============================================================================


class RumorRateLimiter:
    """Limits how many rumor SMS are sent per hour."""

    def __init__(self, max_per_hour: int):
        self.max_per_hour = max_per_hour
        self.sent_timestamps: list = []

    def can_send(self) -> bool:
        """Check if we can send another rumor SMS."""
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        # Remove timestamps older than 1 hour
        self.sent_timestamps = [ts for ts in self.sent_timestamps if ts > one_hour_ago]
        return len(self.sent_timestamps) < self.max_per_hour

    def record_sent(self) -> None:
        """Record that a rumor SMS was sent."""
        self.sent_timestamps.append(datetime.utcnow())


# =============================================================================
# TICKER WATCHER - Monitors for when a ticker starts trading
# =============================================================================

WATCHED_TICKERS_FILE = "watched_tickers.json"


class TickerWatcher:
    """
    Watches ticker symbols and alerts when they start trading.

    Once a confirmed IPO alert includes a ticker symbol, it gets added to the
    watch list. The watcher checks every cycle if the ticker is live on an exchange.
    """

    def __init__(self):
        self.watched_tickers: dict = {}  # {ticker: {"added": iso_date, "notified": bool}}
        self._load()

    def _load(self):
        """Load watched tickers from disk."""
        path = Path(WATCHED_TICKERS_FILE)
        if path.exists():
            try:
                with open(path, "r") as f:
                    self.watched_tickers = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load watched tickers: {e}")
                self.watched_tickers = {}

    def _save(self):
        """Save watched tickers to disk."""
        path = Path(WATCHED_TICKERS_FILE)
        try:
            with open(path, "w") as f:
                json.dump(self.watched_tickers, f, indent=2)
        except IOError as e:
            logger.error(f"Could not save watched tickers: {e}")

    def add_ticker(self, ticker: str):
        """Add a ticker to the watch list."""
        if ticker and ticker not in self.watched_tickers:
            self.watched_tickers[ticker] = {
                "added": datetime.utcnow().isoformat(),
                "notified": False,
            }
            self._save()
            logger.info(f"📊 Added ticker '{ticker}' to watch list")

    def check_all(self, notifier: BaseNotifier) -> None:
        """
        Check all watched tickers to see if any are now trading.

        Args:
            notifier: The notification service to send alerts.
        """
        if not self.watched_tickers:
            return

        tickers_to_check = [
            t for t, info in self.watched_tickers.items()
            if not info.get("notified", False)
        ]

        if not tickers_to_check:
            return

        logger.info(f"📊 Checking {len(tickers_to_check)} watched ticker(s): {', '.join(tickers_to_check)}")

        for ticker in tickers_to_check:
            quote = check_ticker_live(ticker)
            if quote:
                # TRADING HAS STARTED!
                price = quote["price"]
                exchange = quote["exchange"]
                name = quote["name"]
                currency = quote["currency"]
                market_state = quote["market_state"]

                message = (
                    f"🔔 TRADING HAS STARTED!\n\n"
                    f"SpaceX ({ticker}) is NOW LIVE!\n"
                    f"💰 Price: ${price:.2f} {currency}\n"
                    f"📈 Exchange: {exchange}\n"
                    f"🏷️ Name: {name}\n"
                    f"📊 Market State: {market_state}\n"
                    f"🕐 Detected: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                    f"GO GO GO! 🚀"
                )

                logger.info(f"🔔 TRADING STARTED: {ticker} at ${price:.2f} on {exchange}")
                notifier.send_alert(message, "confirmed")

                # Mark as notified so we don't alert again
                self.watched_tickers[ticker]["notified"] = True
                self.watched_tickers[ticker]["trading_started"] = datetime.utcnow().isoformat()
                self.watched_tickers[ticker]["first_price"] = price
                self._save()
            else:
                logger.info(f"  {ticker}: Not yet trading")

    def has_active_watches(self) -> bool:
        """Check if there are any tickers being actively watched."""
        return any(
            not info.get("notified", False)
            for info in self.watched_tickers.values()
        )


# =============================================================================
# OPENING BELL SCHEDULER
# =============================================================================

ET = ZoneInfo("America/New_York")

# Opening bell time: 9:30:10 AM ET (10 seconds after NYSE/NASDAQ open)
OPENING_BELL_HOUR = 9
OPENING_BELL_MINUTE = 30
OPENING_BELL_SECOND = 10


def seconds_until_opening_bell() -> float:
    """
    Calculate seconds until the next weekday opening bell (9:30:10 AM ET).

    Returns:
        Seconds until the next opening bell, or float('inf') if the feature
        is disabled via config.
    """
    if not getattr(config, "OPENING_BELL_CHECK", True):
        return float("inf")

    now_et = datetime.now(ET)

    # Build today's bell time
    bell_today = now_et.replace(
        hour=OPENING_BELL_HOUR,
        minute=OPENING_BELL_MINUTE,
        second=OPENING_BELL_SECOND,
        microsecond=0,
    )

    # If today is a weekday and the bell hasn't passed yet, use today
    if now_et.weekday() < 5 and now_et < bell_today:
        delta = (bell_today - now_et).total_seconds()
        return delta

    # Otherwise, find the next weekday
    days_ahead = 1
    next_day = now_et + timedelta(days=days_ahead)
    while next_day.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
        days_ahead += 1
        next_day = now_et + timedelta(days=days_ahead)

    bell_next = next_day.replace(
        hour=OPENING_BELL_HOUR,
        minute=OPENING_BELL_MINUTE,
        second=OPENING_BELL_SECOND,
        microsecond=0,
    )
    delta = (bell_next - now_et).total_seconds()
    return delta


# =============================================================================
# MAIN BOT LOGIC
# =============================================================================


def format_message(article: Article) -> str:
    """Format an article into an SMS message body."""
    parts = []

    if article.alert_level == "confirmed":
        parts.append("SpaceX is going public!")
    else:
        parts.append("SpaceX IPO news detected.")

    parts.append(f"\n📝 {article.title}")

    if article.ticker_symbol:
        parts.append(f"\n💹 Ticker: {article.ticker_symbol}")

    if article.rumored_date:
        parts.append(f"\n📅 Rumored timeframe: {article.rumored_date}")

    parts.append(f"\n📰 Source: {article.source}")
    parts.append(f"\n🔗 {article.url}")

    return "".join(parts)


def run_check(
    notifier: BaseNotifier,
    seen_articles: Set[str],
    rumor_limiter: RumorRateLimiter,
    ticker_watcher: TickerWatcher = None,
) -> Set[str]:
    """
    Run one check cycle: fetch sources, deduplicate, notify.

    Args:
        notifier: The notification service to use.
        seen_articles: Set of already-seen article URLs.
        rumor_limiter: Rate limiter for rumor notifications.
        ticker_watcher: Ticker watcher to add newly discovered tickers.

    Returns:
        Updated set of seen articles.
    """
    logger.info("=" * 50)
    logger.info("Starting check cycle...")

    articles = check_all_sources()

    new_articles = [a for a in articles if a.url not in seen_articles]

    if not new_articles:
        logger.info("No new articles found.")
        return seen_articles

    logger.info(f"Found {len(new_articles)} new article(s).")

    # Prioritize confirmed over rumors
    confirmed = [a for a in new_articles if a.alert_level == "confirmed"]
    rumors = [a for a in new_articles if a.alert_level == "rumor"]

    # Send confirmed alerts immediately (no rate limiting)
    for article in confirmed:
        message = format_message(article)
        logger.info(f"CONFIRMED ALERT: {article.title}")
        success = notifier.send_alert(message, "confirmed")
        if success:
            seen_articles.add(article.url)
            # Add ticker to watch list if found
            if article.ticker_symbol and ticker_watcher:
                ticker_watcher.add_ticker(article.ticker_symbol)

    # Send rumor alerts with rate limiting
    for article in rumors:
        if not rumor_limiter.can_send():
            logger.info("Rumor rate limit reached. Skipping remaining rumors this cycle.")
            break

        message = format_message(article)
        logger.info(f"RUMOR ALERT: {article.title}")
        if article.rumored_date:
            logger.info(f"  Rumored date: {article.rumored_date}")
        success = notifier.send_alert(message, "rumor")
        if success:
            seen_articles.add(article.url)
            rumor_limiter.record_sent()

    # Save updated seen articles
    save_seen_articles(seen_articles)

    return seen_articles


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="SpaceX IPO Notification Bot")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run once with console output (no SMS sent)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check cycle and exit",
    )
    args = parser.parse_args()

    # Override to console notifier for testing
    if args.test:
        config.NOTIFIER = "console"

    # Create notifier
    notifier = create_notifier(config)
    logger.info(f"Using notifier: {config.NOTIFIER}")

    # Load seen articles
    seen_articles = load_seen_articles()
    logger.info(f"Loaded {len(seen_articles)} previously seen articles.")

    # Rate limiter for rumors
    rumor_limiter = RumorRateLimiter(max_per_hour=config.MAX_RUMOR_SMS_PER_HOUR)

    # Ticker watcher - monitors for when discovered tickers start trading
    ticker_watcher = TickerWatcher()
    if ticker_watcher.has_active_watches():
        logger.info(f"📊 Watching {len([t for t, i in ticker_watcher.watched_tickers.items() if not i.get('notified')])} ticker(s) for trading start")

    # Graceful shutdown handler
    running = True

    def signal_handler(sig, frame):
        nonlocal running
        logger.info("\nShutdown signal received. Saving state and exiting...")
        save_seen_articles(seen_articles)
        running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Banner
    logger.info("=" * 60)
    logger.info("  🚀 SpaceX IPO Notification Bot Started")
    logger.info(f"  Check interval: {config.CHECK_INTERVAL_SECONDS}s ({config.CHECK_INTERVAL_SECONDS // 60} min)")
    logger.info(f"  Max rumor SMS/hour: {config.MAX_RUMOR_SMS_PER_HOUR}")
    logger.info(f"  Notifier: {config.NOTIFIER}")
    logger.info("=" * 60)

    if args.once or args.test:
        # Single run
        seen_articles = run_check(notifier, seen_articles, rumor_limiter, ticker_watcher)
        # Also check watched tickers
        ticker_watcher.check_all(notifier)
        logger.info("Single check complete. Exiting.")
        return

    # Continuous monitoring loop
    while running:
        try:
            seen_articles = run_check(notifier, seen_articles, rumor_limiter, ticker_watcher)
            # Check if any watched tickers have started trading
            ticker_watcher.check_all(notifier)
        except Exception as e:
            logger.error(f"Error during check cycle: {e}", exc_info=True)

        # Smart sleep: wake at whichever comes first — regular interval or opening bell
        bell_seconds = seconds_until_opening_bell()
        interval_seconds = float(config.CHECK_INTERVAL_SECONDS)
        sleep_seconds = min(interval_seconds, bell_seconds)

        is_bell_wake = bell_seconds <= interval_seconds

        if is_bell_wake and bell_seconds < float("inf"):
            bell_time_et = datetime.now(ET) + timedelta(seconds=bell_seconds)
            logger.info(
                f"🔔 Next wake: opening bell at {bell_time_et.strftime('%H:%M:%S ET')} "
                f"(in {int(bell_seconds)}s)"
            )
        else:
            logger.info(f"Next check in {config.CHECK_INTERVAL_SECONDS // 60} minutes...")

        time.sleep(sleep_seconds)

        # If we woke for the opening bell, only do a ticker check (not full source scan)
        if is_bell_wake and bell_seconds < float("inf") and sleep_seconds < interval_seconds:
            try:
                logger.info("🔔 Opening bell ticker check!")
                ticker_watcher.check_all(notifier)
            except Exception as e:
                logger.error(f"Error during opening bell ticker check: {e}", exc_info=True)

            # Sleep remaining time until the next regular interval
            remaining = interval_seconds - sleep_seconds
            if remaining > 0:
                logger.info(f"Next full check in {int(remaining)}s...")
                time.sleep(remaining)


if __name__ == "__main__":
    main()
