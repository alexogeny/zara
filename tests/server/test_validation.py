import asyncio
import unittest
import urllib.parse
from typing import Any, Dict
from unittest.mock import AsyncMock

from tests.helpers import assert_status_code_with_response_body, make_test_app


class TestValidatorWithQueryString(unittest.TestCase):
    def setUp(self):
        self.app = make_test_app()

    async def simulate_asgi_request(
        self,
        path: str,
        method: str,
        headers: Dict[bytes, bytes],
        query_params: Dict[str, Any] = None,
    ):
        query_string = urllib.parse.urlencode(query_params or {}).encode("utf-8")
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(k, v) for k, v in headers.items()],
            "query_string": query_string,
        }
        receive = lambda: None
        send = AsyncMock()

        await self.app(scope, receive, send)
        return send

    def test_search_with_missing_email(self):
        query_params = {
            "receive_marketing": "true",
            # "email" is intentionally missing to test validation
        }
        send = asyncio.run(
            self.simulate_asgi_request("/register", "GET", {}, query_params)
        )
        assert_status_code_with_response_body(
            send,
            400,
            b'{"errors": [{"field": "email", "message": "Email is required when receiving marketing communications."}]}',
            headers=[(b"content-type", b"application/json")],
        )

    def test_search_with_email(self):
        query_params = {
            "receive_marketing": "true",
            "email": "user@example.com",
        }
        send = asyncio.run(
            self.simulate_asgi_request("/register", "GET", {}, query_params)
        )
        assert_status_code_with_response_body(send, 200, b"Registered!")
