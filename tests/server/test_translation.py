import asyncio
import unittest
import urllib.parse
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

from tests.helpers import assert_status_code_with_response_body, make_test_app
from zara.server.translation import I18n


class TestTranslation(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(I18n, "load_translations", self.mock_load_translations)
        self.addCleanup(patcher.stop)
        self.mock_load_translations = patcher.start()
        self.app = make_test_app()

    def mock_load_translations(*args, **kwargs):
        """Mock method to replace the actual load_translations."""
        return {
            "en": {
                "messages": {
                    "people": {
                        "count": {
                            "zero": "There are zero people.",
                            "one": "There is one person.",
                            "few": "There are {amount_of_people} people.",
                            "many": "There are many people.",
                        }
                    },
                }
            }
        }

    async def simulate_asgi_request(
        self,
        path: str,
        method: str,
        headers: Dict[bytes, bytes] = {},
        query_params: Dict[str, Any] = None,
    ):
        query_string = urllib.parse.urlencode(query_params or {})
        scope = {
            "type": "http",
            "method": method,
            "path": path + "?" + query_string if query_string else path,
            "headers": [(k, v) for k, v in headers.items()],
        }
        receive = lambda: None
        send = AsyncMock()

        await self.app(scope, receive, send)
        return send

    def test_get_zero(self):
        send = asyncio.run(
            self.simulate_asgi_request("/translated", "GET", query_params={"count": 0})
        )
        assert_status_code_with_response_body(send, 200, b"There are zero people.")

    def test_get_one(self):
        send = asyncio.run(
            self.simulate_asgi_request("/translated", "GET", query_params={"count": 1})
        )
        assert_status_code_with_response_body(send, 200, b"There is one person.")

    def test_get_few(self):
        send = asyncio.run(
            self.simulate_asgi_request("/translated", "GET", query_params={"count": 3})
        )
        assert_status_code_with_response_body(send, 200, b"There are 3 people.")

    def test_get_many(self):
        send = asyncio.run(
            self.simulate_asgi_request("/translated", "GET", query_params={"count": 10})
        )
        assert_status_code_with_response_body(send, 200, b"There are many people.")
