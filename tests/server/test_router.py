import unittest
from typing import Any, Dict
from unittest.mock import AsyncMock

from tests.helpers import assert_status_code_with_response_body, make_scope
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

        scope = make_scope()
        await run_app_with_scope(scope)
        assert_status_code_with_response_body(send_mock, 200, b"Hello, World!")

        scope = make_scope(path="/goodbye", method="POST")
        send_mock.reset_mock()
        await run_app_with_scope(scope)
        assert_status_code_with_response_body(send_mock, 200, b"Goodbye, World!")
