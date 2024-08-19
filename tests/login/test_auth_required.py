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


class TestAuthRequiredDecorator(unittest.TestCase):
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

    def test_access_granted(self):
        token = create_jwt({"user_id": "admin"}, roles=["admin"], permissions=["read"])
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(self.simulate_asgi_request("/authenticated", "GET", headers))
        assert_status_code_with_response_body(send, 200, b"Access granted!")

    def test_access_denied_malformed_token(self):
        token = "invalid_token"
        headers = {
            b"authorization": f"{token}".encode(),
        }
        send = asyncio.run(self.simulate_asgi_request("/authenticated", "GET", headers))
        assert_status_code_with_response_body(
            send,
            403,
            b'{"detail":"Malformed authorization header"}',
            headers=[(b"content-type", b"application/json")],
        )

    def test_access_denied_invalid_token(self):
        token = "invalid_token"
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(self.simulate_asgi_request("/authenticated", "GET", headers))

        assert_status_code_with_response_body(
            send,
            403,
            b'{"detail":"Invalid token"}',
            headers=[(b"content-type", b"application/json")],
        )

    def test_access_denied_insufficient_permissions(self):
        token = create_jwt({"user_id": "user"}, roles=["user"], permissions=["write"])
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(self.simulate_asgi_request("/authenticated", "GET", headers))

        assert_status_code_with_response_body(
            send,
            403,
            b'{"detail":"Insufficient permissions"}',
            headers=[(b"content-type", b"application/json")],
        )

    def test_access_denied_insufficient_roles(self):
        token = create_jwt({"user_id": "user"}, roles=["user"], permissions=["read"])
        headers = {
            b"authorization": f"Bearer {token}".encode(),
        }
        send = asyncio.run(self.simulate_asgi_request("/authenticated", "GET", headers))

        assert_status_code_with_response_body(
            send,
            403,
            b'{"detail":"Insufficient roles"}',
            headers=[(b"content-type", b"application/json")],
        )
