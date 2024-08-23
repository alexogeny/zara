from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Callable, Dict, List


class Channel(Enum):
    EMAIL = auto()
    SMS = auto()
    SLACK = auto()
    LOG = auto()
    CUSTOM = auto()


class NotificationHandler(ABC):
    @abstractmethod
    async def handle(self, message: Any) -> None:
        pass


class EmailNotificationHandler(NotificationHandler):
    async def handle(self, message: Any) -> None:
        print(f"Email sent with message: {message}")


class SMSNotificationHandler(NotificationHandler):
    async def handle(self, message: Any) -> None:
        print(f"SMS sent with message: {message}")


class SlackNotificationHandler(NotificationHandler):
    async def handle(self, message: Any) -> None:
        print(f"Slack message sent with message: {message}")


class LogNotificationHandler(NotificationHandler):
    async def handle(self, message: Any) -> None:
        print(f"Log message: {message}")


class CustomNotificationHandler(NotificationHandler):
    async def handle(self, message: Any) -> None:
        print(f"Custom notification: {message}")


class NotificationChannelRegistry:
    _handlers = {
        Channel.EMAIL: EmailNotificationHandler,
        Channel.SMS: SMSNotificationHandler,
        Channel.SLACK: SlackNotificationHandler,
        Channel.LOG: LogNotificationHandler,
        Channel.CUSTOM: CustomNotificationHandler,
    }

    @classmethod
    def get_handler(cls, channel: Channel) -> NotificationHandler:
        handler_class = cls._handlers.get(channel)
        if not handler_class:
            raise ValueError(f"No handler registered for channel {channel}")
        return handler_class()


class Notification(ABC):
    default_resolvers: Dict[Channel, Callable[[], Any]] = {}

    def __init__(
        self,
        channels: List[Channel],
        resolvers: Dict[Channel, Callable[[], Any]] = None,
    ) -> None:
        self.channels = channels
        self.resolvers = resolvers or {}
        self.handler_map = self._get_handler_map()

    def _get_handler_map(self) -> Dict[Channel, Callable[[Any], NotificationHandler]]:
        return {
            channel: NotificationChannelRegistry.get_handler(channel)
            for channel in self.channels
        }

    async def send(self) -> None:
        for channel in self.channels:
            resolver = self.resolvers.get(channel) or self.default_resolvers.get(
                channel
            )
            if not resolver:
                raise ValueError(
                    f"No resolver provided for channel {channel} and no default resolver available."
                )
            message = resolver()
            handler = self.handler_map.get(channel)
            if handler:
                await handler.handle(message)
