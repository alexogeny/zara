import unittest
from typing import Any, Dict
from unittest.mock import AsyncMock

from zara.server.router import Router
from zara.server.server import SimpleASGIApp


class TestRouter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.router = Router()

    async def async_hello_world(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
            "body": b"Hello, World!",
        }

    async def async_goodbye_world(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
            "body": b"Goodbye, World!",
        }

    async def test_routing(self):
        app = SimpleASGIApp()
        app.add_router(self.router)

        @self.router.get("/")
        async def hello_world(request: Dict[str, Any]) -> Dict[str, Any]:
            return await self.async_hello_world(request)

        @self.router.post("/goodbye")
        async def goodbye_world(request: Dict[str, Any]) -> Dict[str, Any]:
            return await self.async_goodbye_world(request)

        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await app(scope, None, send_mock)

        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [],
            "query_string": b"",
        }
        await run_app_with_scope(scope)

        send_mock.assert_any_call(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        send_mock.assert_any_call(
            {
                "type": "http.response.body",
                "body": b"Hello, World!",
            }
        )

        scope = {
            "type": "http",
            "path": "/goodbye",
            "method": "POST",
            "headers": [],
            "query_string": b"",
        }
        send_mock.reset_mock()
        await run_app_with_scope(scope)

        send_mock.assert_any_call(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        send_mock.assert_any_call(
            {
                "type": "http.response.body",
                "body": b"Goodbye, World!",
            }
        )
