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

    def __init__(self, account_sid: str, auth_token: str, from_number: str, to_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_number = to_number
        self._client = None

    @property
    def client(self):
        """Lazy-load the Twilio client."""
        if self._client is None:
            from twilio.rest import Client
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    def send_alert(self, message: str, alert_level: str) -> bool:
        """Send an SMS via Twilio."""
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

            msg = self.client.messages.create(
                body=full_message,
                from_=self.from_number,
                to=self.to_number,
            )
            logger.info(f"SMS sent successfully. SID: {msg.sid}")
            return True

        except Exception as e:
            logger.error(f"Failed to send SMS via Twilio: {e}")
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
        return TwilioNotifier(
            account_sid=config.TWILIO_ACCOUNT_SID,
            auth_token=config.TWILIO_AUTH_TOKEN,
            from_number=config.TWILIO_FROM_NUMBER,
            to_number=config.YOUR_PHONE_NUMBER,
        )
    elif notifier_type == "console":
        return ConsoleNotifier()
    else:
        raise ValueError(
            f"Unknown notifier type: '{notifier_type}'. "
            f"Available options: 'twilio', 'console'"
        )
