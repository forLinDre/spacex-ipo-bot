"""
Notification module for SpaceX IPO Bot.

Provides an abstract base class and concrete implementations for sending alerts.
To add a new provider, subclass BaseNotifier and update the factory function.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseNotifier(ABC):
    """Abstract base class for all notification providers."""

    @abstractmethod
    def send_alert(self, message: str, alert_level: str) -> bool:
        """
        Send a notification message.

        Args:
            message: The message body to send.
            alert_level: Either 'confirmed' or 'rumor'.

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        pass


class TwilioNotifier(BaseNotifier):
    """Twilio SMS notification implementation."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str, to_numbers: list):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_numbers = to_numbers if isinstance(to_numbers, list) else [to_numbers]
        self._client = None

    @property
    def client(self):
        """Lazy-load the Twilio client."""
        if self._client is None:
            from twilio.rest import Client
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    def send_alert(self, message: str, alert_level: str) -> bool:
        """Send an SMS via Twilio to all configured phone numbers."""
        try:
            # Prefix message with alert level indicator
            if alert_level == "confirmed":
                prefix = "🚀 CONFIRMED IPO ALERT"
            else:
                prefix = "📰 IPO RUMOR"

            full_message = f"{prefix}\n\n{message}"

            # Twilio SMS limit is 1600 chars
            if len(full_message) > 1600:
                full_message = full_message[:1597] + "..."

            all_sent = True
            for to_number in self.to_numbers:
                try:
                    msg = self.client.messages.create(
                        body=full_message,
                        from_=self.from_number,
                        to=to_number,
                    )
                    logger.info(f"SMS sent to {to_number}. SID: {msg.sid}")
                except Exception as e:
                    logger.error(f"Failed to send SMS to {to_number}: {e}")
                    all_sent = False

            return all_sent

        except Exception as e:
            logger.error(f"Failed to send SMS via Twilio: {e}")
            return False


class CallMeBotNotifier(BaseNotifier):
    """CallMeBot WhatsApp notification implementation (free, no library needed)."""

    CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

    def __init__(self, recipients: list):
        """
        Args:
            recipients: List of dicts with 'phone' and 'apikey' keys.
                        Example: [{"phone": "+14155551234", "apikey": "123456"}]
        """
        self.recipients = recipients

    def send_alert(self, message: str, alert_level: str) -> bool:
        """Send a WhatsApp message via CallMeBot to all configured recipients."""
        import requests
        import urllib.parse
        import time

        try:
            if alert_level == "confirmed":
                prefix = "🚀 CONFIRMED IPO ALERT"
            else:
                prefix = "📰 IPO RUMOR"

            full_message = f"{prefix}\n\n{message}"

            all_sent = True
            for recipient in self.recipients:
                try:
                    params = {
                        "phone": recipient["phone"],
                        "text": full_message,
                        "apikey": recipient["apikey"],
                    }
                    response = requests.get(self.CALLMEBOT_URL, params=params, timeout=30)

                    if response.status_code == 200:
                        logger.info(f"WhatsApp message sent to {recipient['phone']}")
                    else:
                        logger.error(
                            f"CallMeBot returned status {response.status_code} "
                            f"for {recipient['phone']}: {response.text}"
                        )
                        all_sent = False

                    # CallMeBot rate limit: wait between messages
                    time.sleep(2)

                except Exception as e:
                    logger.error(f"Failed to send WhatsApp to {recipient['phone']}: {e}")
                    all_sent = False

            return all_sent

        except Exception as e:
            logger.error(f"Failed to send WhatsApp via CallMeBot: {e}")
            return False


class ConsoleNotifier(BaseNotifier):
    """Console/stdout notification (useful for testing)."""

    def send_alert(self, message: str, alert_level: str) -> bool:
        """Print the alert to console."""
        if alert_level == "confirmed":
            prefix = "🚀 CONFIRMED IPO ALERT"
        else:
            prefix = "📰 IPO RUMOR"

        print(f"\n{'='*60}")
        print(f"  {prefix}")
        print(f"{'='*60}")
        print(f"  {message}")
        print(f"{'='*60}\n")
        return True


def create_notifier(config) -> BaseNotifier:
    """
    Factory function to create the appropriate notifier based on config.

    To add a new provider:
    1. Create a new class that extends BaseNotifier
    2. Add a new elif branch here
    3. Update config.py with the new provider's settings

    Args:
        config: The config module with notification settings.

    Returns:
        An instance of BaseNotifier.
    """
    notifier_type = getattr(config, "NOTIFIER", "twilio").lower()

    if notifier_type == "twilio":
        # Support both old (YOUR_PHONE_NUMBER string) and new (PHONE_NUMBERS list) config
        to_numbers = getattr(config, "PHONE_NUMBERS", None)
        if to_numbers is None:
            # Fallback to old single-number config
            to_numbers = [getattr(config, "YOUR_PHONE_NUMBER", "")]

        return TwilioNotifier(
            account_sid=config.TWILIO_ACCOUNT_SID,
            auth_token=config.TWILIO_AUTH_TOKEN,
            from_number=config.TWILIO_FROM_NUMBER,
            to_numbers=to_numbers,
        )
    elif notifier_type == "callmebot":
        recipients = getattr(config, "CALLMEBOT_RECIPIENTS", [])
        if not recipients:
            raise ValueError(
                "CALLMEBOT_RECIPIENTS must be set in config.py. "
                "Example: [{'phone': '+14155551234', 'apikey': '123456'}]"
            )
        return CallMeBotNotifier(recipients=recipients)
    elif notifier_type == "console":
        return ConsoleNotifier()
    else:
        raise ValueError(
            f"Unknown notifier type: '{notifier_type}'. "
            f"Available options: 'twilio', 'callmebot', 'console'"
        )
