import asyncio
import unittest
from datetime import datetime, timedelta
from enum import auto
from typing import Dict
from unittest.mock import AsyncMock, patch

from tests.helpers import (
    assert_status_code_with_response_body,
    make_scope,
    make_test_app,
)
from zara.server.events import Action, BaseEventName, Event, Listener, extend_enum

test_event_names = {"TEST_EVENT": auto()}

TestEventName = extend_enum(BaseEventName, test_event_names)


async def load_test_events():
    return []


async def save_test_events(events_data):
    return True


class TestAuthRequiredDecorator(unittest.TestCase):
    def _patch_datetime(self):
        patcher = patch("zara.server.events.datetime")
        mock_datetime = patcher.start()
        self.addCleanup(patcher.stop)

        mock_datetime.now.side_effect = lambda: datetime.fromtimestamp(
            self.current_time
        )
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        return mock_datetime

    def setUp(self):
        self.app = make_test_app()
        self.events_triggered = asyncio.Queue()
        self.current_time = 1704100800.0

        class TestAction(Action):
            def __init__(self, events_queue):
                self.events_queue = events_queue

            async def execute(self, event: Event) -> None:
                await self.events_queue.put(event)

        class TestListener(Listener):
            pass

        test_listener = TestListener(
            TestEventName.TEST_EVENT, TestAction(self.events_triggered)
        )
        self.app.add_listener(test_listener)

    def _increment_time(self, seconds):
        self.current_time += seconds

    async def asyncSetUp(self):
        await self.app.startup(load_test_events)

    async def asyncTearDown(self):
        await self.app.shutdown(save_test_events)

    async def simulate_asgi_request(
        self, path: str, method: str, headers: Dict[bytes, bytes] = {}
    ):
        scope = make_scope(
            path=path, method=method, headers=[(k, v) for k, v in headers.items()]
        )
        send = AsyncMock()

        await self.app(scope, None, send)
        return send

    async def _schedule_test_event(
        self, increment=None, trigger=None, time=None, delta=None
    ):
        self.app.schedule_event(
            TestEventName.TEST_EVENT, None, delay=timedelta(seconds=delta)
        )
        send = await self.simulate_asgi_request("/", "GET")

        try:
            self._increment_time(increment)
            event = await asyncio.wait_for(self.events_triggered.get(), timeout=0.15)
            if trigger is True:
                assert event is not None
                assert event.trigger_time.timestamp() == time
                assert event.event_name == TestEventName.TEST_EVENT
            elif trigger is False:
                assert event is None
        except asyncio.TimeoutError:
            if trigger is False:
                pass
            else:
                self.fail("The event was not triggered within the expected time frame.")
        return send

    def test_scheduled_events_get_fired(
        self,
    ):
        self._patch_datetime()

        asyncio.run(
            self._run_scheduled_event_test(
                increment=0.1, trigger=True, time=self.current_time + 0.1, delta=0.1
            )
        )

    def test_scheduled_events_dont_fire(
        self,
    ):
        self._patch_datetime()

        asyncio.run(
            self._run_scheduled_event_test(
                increment=0.1, trigger=False, time=self.current_time + 0.1, delta=10
            )
        )

    async def _run_scheduled_event_test(
        self, increment=None, trigger=None, time=None, delta=None
    ):
        await self.asyncSetUp()
        send = await self._schedule_test_event(
            increment=increment, trigger=trigger, time=time, delta=delta
        )
        await self.asyncTearDown()

        assert_status_code_with_response_body(send, 200, b"Hello, World!")
