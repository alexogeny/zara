import asyncio
import unittest
from typing import Dict
from unittest.mock import AsyncMock

from tests.helpers import (
    assert_status_code_with_response_body,
    make_scope,
    make_test_app,
)
from zara.login.jwt import create_jwt


class TestApplyRateLimitDecorator(unittest.TestCase):
    def setUp(self):
        self.app = make_test_app()

    async def simulate_asgi_request(
        self, path: str, method: str, headers: Dict[bytes, bytes]
    ):
        scope = make_scope(
            path=path, method=method, headers=[(k, v) for k, v in headers.items()]
        )
        send = AsyncMock()

        await self.app(scope, None, send)
        return send

    def test_not_rate_limited(self):
        token = create_jwt({"user_id": "admin"}, roles=["admin"], permissions=["read"])
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(self.simulate_asgi_request("/rate-limited", "GET", headers))
        assert_status_code_with_response_body(send, 200, b"Not rate limited!")

    def test_should_be_route_rate_limited(self):
        token = create_jwt({"user_id": "admin"}, roles=["admin"], permissions=["read"])
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(self.simulate_asgi_request("/rate-limited", "GET", headers))
        assert_status_code_with_response_body(send, 200, b"Not rate limited!")
        send = asyncio.run(self.simulate_asgi_request("/rate-limited", "GET", headers))
        assert_status_code_with_response_body(
            send,
            429,
            b'{"detail":"Rate limit exceeded"}',
            headers=[(b"content-type", b"application/json")],
        )

    def test_should_be_router_rate_limited(self):
        token = create_jwt({"user_id": "admin"}, roles=["admin"], permissions=["read"])
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(
            self.simulate_asgi_request("/rate-limited-router", "GET", headers)
        )
        assert_status_code_with_response_body(send, 200, b"Not rate limited!")
        send = asyncio.run(
            self.simulate_asgi_request("/rate-limited-router", "GET", headers)
        )
        assert_status_code_with_response_body(send, 200, b"Not rate limited!")
        send = asyncio.run(
            self.simulate_asgi_request("/rate-limited-router", "GET", headers)
        )
        assert_status_code_with_response_body(
            send,
            429,
            b'{"detail":"Rate limit exceeded"}',
            headers=[(b"content-type", b"application/json")],
        )

    def test_should_be_server_rate_limited(self):
        token = create_jwt({"user_id": "admin"}, roles=["admin"], permissions=["read"])
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(
            self.simulate_asgi_request("/two/rate-limited-server", "GET", headers)
        )
        assert_status_code_with_response_body(send, 200, b"Not rate limited!")
        send = asyncio.run(
            self.simulate_asgi_request("/two/rate-limited-server", "GET", headers)
        )
        assert_status_code_with_response_body(send, 200, b"Not rate limited!")
        send = asyncio.run(
            self.simulate_asgi_request("/two/rate-limited-server", "GET", headers)
        )
        assert_status_code_with_response_body(send, 200, b"Not rate limited!")
        send = asyncio.run(
            self.simulate_asgi_request("/two/rate-limited-server", "GET", headers)
        )
        assert_status_code_with_response_body(
            send,
            429,
            b'{"detail":"Rate limit exceeded"}',
            headers=[(b"content-type", b"application/json")],
        )
