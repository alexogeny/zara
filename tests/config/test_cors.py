import unittest
from typing import Any, Dict
from unittest.mock import AsyncMock, mock_open, patch

from zara.config.config import Config
from zara.server.router import Router
from zara.server.server import SimpleASGIApp


class TestCORS(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        config_content = """
        [server]
        port = 8080
        host = 127.0.0.1

        [cors]
        allowed_origins = https://example.com, https://another.com
        allowed_methods = GET, POST, OPTIONS
        allowed_headers = Content-Type, Authorization
        allow_credentials = true
        """
        with patch("builtins.open", mock_open(read_data=config_content)):
            self.config = Config("config.ini")

        self.app = SimpleASGIApp()
        self.router = Router()

        @self.router.route(path="/", method="GET")
        async def hello_world(request: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
                "body": b"Hello, World!",
            }

        self.app.add_router(self.router)

    async def test_cors_headers(self):
        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await self.app(scope, None, send_mock)

        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [(b"origin", b"https://example.com")],
            "query_string": b"",
        }

        await run_app_with_scope(scope)
        send_mock.assert_any_await(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"access-control-allow-origin", b"https://example.com"),
                    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                    (b"access-control-allow-headers", b"Content-Type, Authorization"),
                    (b"access-control-allow-credentials", b"true"),
                ],
            }
        )
        send_mock.assert_any_await(
            {
                "type": "http.response.body",
                "body": b"Hello, World!",
            }
        )

    async def test_cors_no_origin(self):
        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await self.app(scope, None, send_mock)

        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [],
            "query_string": b"",
        }

        await run_app_with_scope(scope)
        send_mock.assert_any_await(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        send_mock.assert_any_await(
            {
                "type": "http.response.body",
                "body": b"Hello, World!",
            }
        )

    async def test_cors_not_allowed_origin(self):
        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await self.app(scope, None, send_mock)

        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [(b"origin", b"https://notallowed.com")],
            "query_string": b"",
        }

        await run_app_with_scope(scope)

        send_mock.assert_any_await(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        send_mock.assert_any_await(
            {
                "type": "http.response.body",
                "body": b"Hello, World!",
            }
        )
