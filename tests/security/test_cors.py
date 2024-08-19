import unittest
from unittest.mock import AsyncMock

from ..helpers import assert_status_code_with_response_body, make_scope, make_test_app


class TestCORS(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {
            "server": {"port": "8080", "host": "127.0.0.1"},
            "cors": {
                "allowed_origins": "https://example.com, https://another.com",
                "allowed_methods": "GET, POST, OPTIONS",
                "allowed_headers": "Content-Type, Authorization",
                "allow_credentials": "true",
            },
        }
        self.app = make_test_app(config=self.config)

    async def test_cors_headers(self):
        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await self.app(scope, None, send_mock)

        scope = make_scope(headers=[(b"origin", b"https://example.com")])

        await run_app_with_scope(scope)
        assert_status_code_with_response_body(
            send_mock,
            200,
            b"Hello, World!",
            headers=[
                (b"content-type", b"text/plain"),
                (b"access-control-allow-origin", b"https://example.com"),
                (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers", b"Content-Type, Authorization"),
                (b"access-control-allow-credentials", b"true"),
            ],
        )

    async def test_cors_no_origin(self):
        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await self.app(scope, None, send_mock)

        scope = make_scope()
        await run_app_with_scope(scope)

        assert_status_code_with_response_body(send_mock, 200, b"Hello, World!")

    async def test_cors_not_allowed_origin(self):
        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await self.app(scope, None, send_mock)

        scope = make_scope(headers=[(b"origin", b"https://notallowed.com")])
        await run_app_with_scope(scope)

        assert_status_code_with_response_body(send_mock, 200, b"Hello, World!")
