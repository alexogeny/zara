import unittest
from typing import Any, Dict
from unittest.mock import MagicMock

from zara.server.router import Router
from zara.server.server import SimpleASGIApp


class TestRouter(unittest.TestCase):
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

    async def test_add_and_resolve_route_decorator(self):
        # Use the router as a decorator
        @self.router.add_route(path="/", method="GET")
        async def hello_world(request: Dict[str, Any]) -> Dict[str, Any]:
            return await self.async_hello_world(request)

        @self.router.add_route(path="/goodbye", method="POST")
        async def goodbye_world(request: Dict[str, Any]) -> Dict[str, Any]:
            return await self.async_goodbye_world(request)

        # Resolve the handlers
        handler = await self.router.resolve("/", "GET")
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__name__, "hello_world")

        handler = await self.router.resolve("/goodbye", "POST")
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__name__, "goodbye_world")

        # Test non-existing route
        handler = await self.router.resolve("/notfound", "GET")
        self.assertIsNone(handler)

    async def test_integration_with_app(self):
        app = SimpleASGIApp()
        app.add_router(self.router)

        # Use the router as a decorator
        @self.router.add_route(path="/", method="GET")
        async def hello_world(request: Dict[str, Any]) -> Dict[str, Any]:
            return await self.async_hello_world(request)

        @self.router.add_route(path="/goodbye", method="POST")
        async def goodbye_world(request: Dict[str, Any]) -> Dict[str, Any]:
            return await self.async_goodbye_world(request)

        # Mock the ASGI send callable
        send_mock = MagicMock()

        async def run_app_with_scope(scope):
            await app(scope, None, send_mock)

        # Test GET /
        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [],
            "query_string": b"",
        }
        self.loop.run_until_complete(run_app_with_scope(scope))

        # Check that the correct response was sent
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

        # Test POST /goodbye
        scope = {
            "type": "http",
            "path": "/goodbye",
            "method": "POST",
            "headers": [],
            "query_string": b"",
        }
        send_mock.reset_mock()
        self.loop.run_until_complete(run_app_with_scope(scope))

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
