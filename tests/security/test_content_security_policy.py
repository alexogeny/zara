import unittest
from unittest.mock import AsyncMock

from ..helpers import assert_status_code_with_response_body, make_scope, make_test_app


class TestCSP(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {
            "server": {"port": "8080", "host": "127.0.0.1"},
            "csp": {
                "script": "https://trustedscripts.example.com",
                "style": "https://trustedstyles.example.com",
                "image": "https://trustedimages.example.com",
            },
        }
        self.app = make_test_app(config=self.config)

    async def test_csp_headers(self):
        send_mock = AsyncMock()

        async def run_app_with_scope(scope):
            await self.app(scope, None, send_mock)

        scope = make_scope()

        await run_app_with_scope(scope)
        assert_status_code_with_response_body(
            send_mock,
            200,
            b"Hello, World!",
            headers=[
                (b"content-type", b"text/plain"),
                (
                    b"content-security-policy",
                    (
                        "default-src 'self'; "
                        "script-src 'self' https://trustedscripts.example.com; "
                        "style-src 'self' https://trustedstyles.example.com; "
                        "img-src 'self' data: https://trustedimages.example.com; "
                        "frame-ancestors 'self'; "
                        "form-action 'self'; "
                        "block-all-mixed-content; "
                        "upgrade-insecure-requests"
                    ).encode("utf-8"),
                ),
            ],
        )
