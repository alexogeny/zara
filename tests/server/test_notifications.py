import asyncio
from unittest.mock import patch

from zara.server.notifications import Channel, Notification


class TimeLimitExceededNotification(Notification):
    default_resolvers = {
        Channel.EMAIL: lambda: "Default email content",
        Channel.CUSTOM: lambda: "Default custom channel content",
    }


def test_time_limit_exceeded_notification():
    with patch("builtins.print") as mock_print:
        notification = TimeLimitExceededNotification(
            channels=[Channel.CUSTOM, Channel.EMAIL],
        )
        asyncio.run(notification.send())
        mock_print.assert_any_call(
            "Custom notification: Default custom channel content"
        )
