# 🚀 SpaceX IPO Notification Bot

A Python bot that monitors online sources every 5 minutes for news about SpaceX going public (IPO) and sends you SMS alerts via Twilio.

## Features

- **Multi-source monitoring**: Google News RSS, SEC EDGAR filings, Reddit
- **Two alert levels**:
  - 🚀 **CONFIRMED**: SEC S-1 filings, official announcements
  - 📰 **RUMOR**: News articles, analyst predictions, community discussions
- **Rumored date extraction**: Automatically detects and includes mentioned IPO timeframes (e.g., "Q3 2026", "early 2027")
- **Deduplication**: Tracks seen articles to avoid duplicate notifications
- **Rate limiting**: Configurable max rumor SMS per hour to prevent spam
- **Modular notification system**: Easy to swap Twilio for another SMS/notification provider
- **Graceful shutdown**: Saves state on Ctrl+C

## Quick Start

### 1. Install dependencies

```bash
cd spacex_bot
pip install -r requirements.txt
```

### 2. Configure credentials

Edit `config.py` and fill in:

```python
YOUR_PHONE_NUMBER = "+14155551234"      # Your phone number (with country code)
TWILIO_ACCOUNT_SID = "ACxxxxxxxx..."    # From twilio.com/console
TWILIO_AUTH_TOKEN = "your_auth_token"   # From twilio.com/console
TWILIO_FROM_NUMBER = "+15551234567"     # Your Twilio phone number
```

### 3. Run the bot

```bash
# Production mode (sends real SMS, runs continuously)
python spacex_ipo_bot.py

# Test mode (console output only, runs once, no SMS)
python spacex_ipo_bot.py --test

# Run a single check cycle with SMS then exit
python spacex_ipo_bot.py --once
```

## File Structure

```
spacex_bot/
├── spacex_ipo_bot.py    # Main bot orchestrator (scheduling, dedup, logic)
├── sources.py           # Source checkers (Google News, SEC EDGAR, Reddit)
├── notifier.py          # Abstract notifier interface + Twilio implementation
├── config.py            # Configuration (credentials, intervals, settings)
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

## How It Works

1. Every 5 minutes, the bot queries all configured sources
2. Articles are classified as "confirmed" or "rumor" based on keyword matching
3. New articles (not previously seen) trigger SMS notifications
4. Confirmed alerts are always sent immediately
5. Rumor alerts are rate-limited (default: max 3 per hour)
6. Any mentioned dates/timeframes are extracted and included in the SMS

## Sources Monitored

| Source | What it checks |
|--------|---------------|
| Google News RSS | Multiple search queries for SpaceX IPO news |
| SEC EDGAR | S-1 and S-1/A filings by Space Exploration Technologies Corp |
| Reddit | r/wallstreetbets, r/stocks, r/investing, r/spacex, r/stockmarket |

## Switching Notification Providers

The notification system is modular. To add a new provider:

1. Create a new class in `notifier.py` that extends `BaseNotifier`:

```python
class VonageNotifier(BaseNotifier):
    def __init__(self, api_key, api_secret, from_number, to_number):
        # ...

    def send_alert(self, message: str, alert_level: str) -> bool:
        # Your implementation here
        pass
```

2. Add it to the `create_notifier()` factory function:

```python
elif notifier_type == "vonage":
    return VonageNotifier(...)
```

3. Update `config.py`:

```python
NOTIFIER = "vonage"
VONAGE_API_KEY = "..."
VONAGE_API_SECRET = "..."
```

## Running as a Background Service

### Using systemd (Linux)

Create `/etc/systemd/system/spacex-ipo-bot.service`:

```ini
[Unit]
Description=SpaceX IPO Notification Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/spacex_bot
ExecStart=/usr/bin/python3 spacex_ipo_bot.py
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable spacex-ipo-bot
sudo systemctl start spacex-ipo-bot
```

### Using screen/tmux

```bash
screen -S spacex-bot
python spacex_ipo_bot.py
# Detach with Ctrl+A, D
```

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `CHECK_INTERVAL_SECONDS` | 300 (5 min) | How often to check sources |
| `MAX_RUMOR_SMS_PER_HOUR` | 3 | Max rumor alerts per hour |
| `NOTIFIER` | "twilio" | Notification provider to use |
| `LOG_FILE` | "spacex_ipo_bot.log" | Log file path |
| `SEEN_ARTICLES_FILE` | "seen_articles.json" | Deduplication state file |

## License

Personal use.
