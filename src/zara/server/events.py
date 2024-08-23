import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List


class BaseEventName(Enum):
    BEFORE_REQUEST = auto()
    AFTER_REQUEST = auto()
    STARTUP = auto()
    SHUTDOWN = auto()
    TIME_LIMIT_EXCEEDED = auto()


def utcnow():
    return datetime.now(tz=timezone.utc)


# Event base class
class Event(ABC):
    def __init__(self, event_name: BaseEventName, data: Any = None) -> None:
        self.event_name = event_name
        self.data = data
        self.trigger_time = datetime.now()

    @abstractmethod
    def serialize(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def is_due(self) -> bool:
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, data: Dict[str, Any]) -> "Event":
        pass


class ScheduledEvent(Event):
    def __init__(
        self, event_name: BaseEventName, data: Any, trigger_time: datetime
    ) -> None:
        super().__init__(event_name, data)
        self.trigger_time = trigger_time

    def is_due(self) -> bool:
        return utcnow() >= self.trigger_time

    def serialize(self) -> Dict[str, Any]:
        return {
            "event_name": self.event_name.name,
            "data": self.data,
            "trigger_time": self.trigger_time.isoformat(),
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "ScheduledEvent":
        event_name = BaseEventName[data["event_name"]]
        trigger_time = datetime.fromisoformat(data["trigger_time"])
        return cls(event_name, data["data"], trigger_time)


class ImmediateEvent(Event):
    def is_due(self) -> bool:
        return True

    def serialize(self) -> Dict[str, Any]:
        return {
            "event_name": self.event_name.name,
            "data": self.data,
            "trigger_time": self.trigger_time.isoformat(),
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "ImmediateEvent":
        event_name = BaseEventName[data["event_name"]]
        return cls(event_name, data["data"])


class Action(ABC):
    @abstractmethod
    async def execute(self, event: Event) -> None:
        pass


class Listener(ABC):
    def __init__(self, event_name: BaseEventName, action: Action) -> None:
        self.event_name = event_name
        self.action = action

    async def handle_event(self, event: Event) -> None:
        if event.event_name == self.event_name and event.is_due():
            await self.action.execute(event)


class EventBus:
    def __init__(self) -> None:
        self.queue = asyncio.Queue()
        self.scheduled_events: List[ScheduledEvent] = []
        self._shutdown_event = asyncio.Event()
        self.listeners: List[Listener] = []
        self._app = None

    def set_app(self, app):
        self._app = app

    def register_listener(self, listener: Listener) -> None:
        self.listeners.append(listener)

    def emit(self, event: Event) -> None:
        self.queue.put_nowait(event)

    async def process_events(self) -> None:
        while not self._shutdown_event.is_set():
            self.process_scheduled_events()

            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            for listener in self.listeners:
                await listener.handle_event(event)

            self.queue.task_done()

    def process_scheduled_events(self) -> None:
        due_events = [e for e in self.scheduled_events if e.is_due()]
        for event in due_events:
            self.emit(event)
            self.scheduled_events.remove(event)

    def schedule_event(self, event: ScheduledEvent) -> None:
        self.scheduled_events.append(event)

    def serialize_scheduled_events(self) -> List[Dict[str, Any]]:
        return [event.serialize() for event in self.scheduled_events]

    def deserialize_scheduled_events(self, events_data: List[Dict[str, Any]]) -> None:
        self.scheduled_events = [
            ScheduledEvent.deserialize(data) for data in events_data
        ]

    async def load_scheduled_events(
        self, load_function: Callable[[], List[Dict[str, Any]]]
    ) -> None:
        events_data = await load_function()
        self.deserialize_scheduled_events(events_data)

    async def save_scheduled_events(
        self, save_function: Callable[[List[Dict[str, Any]]], None]
    ) -> None:
        events_data = self.serialize_scheduled_events()
        await save_function(events_data)

    async def start(self) -> None:
        asyncio.create_task(self.process_events())

    async def stop(self, save_function: Callable[[List[Dict[str, Any]]], None]) -> None:
        self._shutdown_event.set()
        await self.queue.join()
        await self.save_scheduled_events(save_function)
