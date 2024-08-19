from unittest.mock import AsyncMock

from zara.server.router import Router
from zara.server.server import SimpleASGIApp


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


def make_test_app():
    app = SimpleASGIApp()
    router = Router()
    app.add_router(router)

    @router.get("/")
    async def hello_world(request):
        return await async_hello_world(request)

    @router.post("/goodbye")
    async def goodbye_world(request):
        return await async_goodbye_world(request)

    @router.get("/authenticated", permissions=["read"], roles=["admin"])
    async def authenticated(request):
        return await async_authenticated(request)

    return app
