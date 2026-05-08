"""
Configuration for SpaceX IPO Notification Bot.

SETUP:
1. Copy this file to config.py:    cp config.example.py config.py
2. Fill in your credentials below
3. Never commit config.py (it's in .gitignore)
"""

# =============================================================================
# NOTIFICATION SETTINGS
# =============================================================================

# Which notifier to use: "twilio", "callmebot", or "console"
NOTIFIER = "callmebot"

# Phone numbers to receive SMS alerts (with country code)
# Add as many numbers as you want to this list
PHONE_NUMBERS = [
    "+1XXXXXXXXXX",  # e.g., "+14155551234"
    # "+1YYYYYYYYYY",  # Add more numbers here
]

# =============================================================================
# CALLMEBOT SETTINGS (Free WhatsApp notifications)
# =============================================================================
# Each recipient must register first by sending this WhatsApp message:
#   "I allow callmebot to send me messages"  →  to +34 644 21 77 47
# They will receive an API key. Add each person's phone + apikey below.

CALLMEBOT_RECIPIENTS = [
    {"phone": "+1XXXXXXXXXX", "apikey": "your_api_key_here"},
    # {"phone": "+1YYYYYYYYYY", "apikey": "another_api_key"},  # Add more recipients
]

# =============================================================================
# TWILIO SETTINGS (alternative to CallMeBot — set NOTIFIER = "twilio" to use)
# =============================================================================

TWILIO_ACCOUNT_SID = "your_account_sid_here"
TWILIO_AUTH_TOKEN = "your_auth_token_here"
TWILIO_FROM_NUMBER = "+1XXXXXXXXXX"  # Your Twilio phone number

# =============================================================================
# BOT SETTINGS
# =============================================================================

# How often to check sources (in seconds)
CHECK_INTERVAL_SECONDS = 300  # 5 minutes

# Maximum rumor SMS per hour (to avoid spam)
MAX_RUMOR_SMS_PER_HOUR = 3

# Log file path
LOG_FILE = "spacex_ipo_bot.log"

# File to track seen articles (for deduplication)
SEEN_ARTICLES_FILE = "seen_articles.json"
