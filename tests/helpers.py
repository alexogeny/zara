from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

from zara.server.router import Router
from zara.server.server import SimpleASGIApp
from zara.server.validation import BaseValidator, validate


@dataclass
class RegisterValidator(BaseValidator):
    receive_marketing: bool
    email: Optional[str] = None

    def validate(self) -> List[Dict[str, Any]]:
        errors = []
        if self.receive_marketing and not self.email:
            errors.append(
                {
                    "field": "email",
                    "message": "Email is required when receiving marketing communications.",
                }
            )
        return errors


def assert_status_code_with_response_body(
    send_mock: AsyncMock, status_code: int, response_body: bytes | str, headers=None
):
    if headers is None:
        headers = [(b"content-type", b"text/plain")]
    assert send_mock.mock_calls[0].args[0]["type"] == "http.response.start"
    assert send_mock.mock_calls[0].args[0]["status"] == status_code
    assert send_mock.mock_calls[0].args[0]["headers"] == headers
    assert send_mock.mock_calls[1].args[0]["type"] == "http.response.body"
    assert send_mock.mock_calls[1].args[0]["body"] == response_body


def make_scope(method="GET", path="/", headers=[]):
    return {
        "type": "http",
        "path": path,
        "method": method,
        "headers": headers,
        "query_string": b"",
    }


async def async_hello_world(request):
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Hello, World!",
    }


async def async_goodbye_world(request):
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Goodbye, World!",
    }


async def async_authenticated(request):
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Access granted!",
    }


async def async_ratelimited(request):
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Not rate limited!",
    }


async def async_register(request):
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Registered!",
    }


async def async_translate(request):
    t = request["t"]
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": t(
            "messages.people.count",
            request["params"]["count"],
            amount_of_people=request["params"]["count"],
        ).encode("utf-8"),
    }


def make_test_app(**kwargs):
    app = SimpleASGIApp(**kwargs)
    app.rate_limit = (3, 5)
    router = Router()
    router.rate_limit = (2, 5)
    app.add_router(router)
    router_two = Router(name="two")
    app.add_router(router_two)

    @router.get("/")
    async def hello_world(request):
        return await async_hello_world(request)

    @router.get("/translated")
    async def translated(request):
        return await async_translate(request)

    @router.post("/goodbye")
    async def goodbye_world(request):
        return await async_goodbye_world(request)

    @router.get("/authenticated", permissions=["read"], roles=["admin"])
    async def authenticated(request):
        return await async_authenticated(request)

    @router.get("/rate-limited", ratelimit=(1, 60))
    async def rate_limited(request):
        return await async_ratelimited(request)

    @router.get("/rate-limited-router")
    async def rate_limited_router(request):
        return await async_ratelimited(request)

    @router_two.get("/rate-limited-server")
    async def rate_limited_server(request):
        return await async_ratelimited(request)

    @router.get("/register")
    @validate(query=RegisterValidator)
    async def register(request):
        return await async_register(request)

    return app
