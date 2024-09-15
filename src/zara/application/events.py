import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List

import orjson
import uvloop

from zara.utilities.logger import setup_logger

# Install uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


class Event:
    def __init__(self, name: str, data: Dict[str, Any] = None, logger=None):
        self.name = name
        self.data = {}
        for key, value in data.items():
            if not hasattr(value, "__dict__"):
                raise ValueError(
                    f"Tried to dispatch a {name} event that doesn't have a __dict__: {key}={value}"
                )
            self.data[key] = value.__dict__
        self.timestamp = datetime.now()
        self._logger = logger

    def serialize(self) -> str:
        return orjson.dumps(
            {
                "name": self.name,
                "data": self.data,
                "timestamp": self.timestamp.isoformat(),
            }
        ).decode()

    @property
    def logger(self):
        if self._logger:
            return self._logger
        return lambda: None

    @staticmethod
    def deserialize(data: str) -> "Event":
        event_dict = orjson.loads(data)
        event = Event(name=event_dict["name"], data=event_dict["data"])
        event.timestamp = datetime.fromisoformat(event_dict["timestamp"])
        return event


class Listener:
    def __init__(self, callback: Callable[[Event], Any]):
        self.callback = callback

    async def notify(self, event: Event):
        await self.callback(event)


class EventBus:
    def __init__(self):
        self._listeners: Dict[str, List[Listener]] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._scheduled_events: List[Event] = []
        self._running = False

    def register_listener(self, event_name: str, listener: Listener):
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(listener)

    def dispatch_event(self, event: Event):
        """Dispatches an event immediately."""
        event._logger = self.logger
        asyncio.create_task(self._queue.put(event))

    def schedule_event(self, event: Event, delay: timedelta):
        """Schedules an event to fire later."""
        fire_time = datetime.now() + delay
        event._logger = self.logger
        asyncio.create_task(self._add_scheduled_event(event, fire_time))

    async def _add_scheduled_event(self, event: Event, fire_time: datetime):
        self.logger.debug("Scheduling event...")
        self._scheduled_events.append((event, fire_time))

    async def start(self):
        self.logger = await setup_logger(
            "EventBus",
            log_file="event-bus.log",
            level=logging.DEBUG,
        )
        self._running = True
        await self._load_scheduled_events()
        asyncio.create_task(self._process_events())

    async def stop(self):
        self._running = False
        await self._serialize_scheduled_events()

    async def _process_events(self):
        """Main event loop to process immediate and scheduled events."""
        while self._running:
            # Process scheduled events first
            now = datetime.now()
            for event, fire_time in self._scheduled_events[:]:
                if now >= fire_time:
                    self.logger.debug("Loaded scheduled event for processing.")
                    await self._queue.put(event)
                    self._scheduled_events.remove((event, fire_time))

            # Process immediate events
            if not self._queue.empty():
                event = await self._queue.get()
                await self._notify_listeners(event)
            await asyncio.sleep(0.1)

    async def _notify_listeners(self, event: Event):
        """Notifies all listeners attached to a particular event."""
        if event.name in self._listeners:
            listeners = self._listeners[event.name]
            for listener in listeners:
                await listener.notify(event)

    async def _load_scheduled_events(self):
        """Load scheduled events from persistent storage at boot time."""
        try:
            with open("scheduled_events.json", "rb") as f:
                data = f.read()
                event_list = orjson.loads(data)
                for event_data in event_list:
                    event = Event.deserialize(event_data["event"])
                    event._logger = self.logger
                    fire_time = datetime.fromisoformat(event_data["fire_time"])
                    self._scheduled_events.append((event, fire_time))
        except FileNotFoundError:
            pass

    async def _serialize_scheduled_events(self):
        """Serialize and store scheduled events that haven't been fired at shutdown."""
        data = []
        for event, fire_time in self._scheduled_events:
            data.append(
                {"event": event.serialize(), "fire_time": fire_time.isoformat()}
            )
        with open("scheduled_events.json", "wb") as f:
            f.write(orjson.dumps(data))
