from http import HTTPStatus
from typing import Any, Dict

import orjson

from .asgi import Send


class Response:
    def Start(status: int = HTTPStatus.OK, headers=[(b"content-type", b"text/plain")]):
        if status in [HTTPStatus.FORBIDDEN]:
            headers = [(b"content-type", b"application/json")]
        return {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }

    def Body(content: bytes):
        return {"type": "http.response.body", "body": content}

    def Error(status: HTTPStatus):
        return {"detail": status.phrase}

    def Detail(message: str):
        return {
            "type": "http.response.body",
            "body": b'{"detail": "' + message.encode("utf-8") + b'"}',
        }


class Http:
    Response = Response
    Status = HTTPStatus


async def send_http_response(
    send: Send,
    status: int,
    body: Dict[Any, Any],
    content_type: str = "application/json",
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", content_type.encode("utf-8")),
            ],
        }
    )

    await send(
        {
            "type": "http.response.body",
            "body": orjson.dumps(body),
        }
    )

async def forbidden(send, reason) -> None:
    await send(Http.Response.Start(status=HTTPStatus.FORBIDDEN))
    await send(Http.Response.Detail(message=reason))

async def send_http_error(send: Send, status: HTTPStatus) -> None:
    await send_http_response(send, status, Http.Response.Error(status))
