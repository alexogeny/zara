from http import HTTPStatus
from typing import Any, Dict

import orjson

from .asgi import Send


class Response:
    Start: str = "http.response.start"
    Body: str = "http.response.body"


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
            "body": orjson.dumps(body).encode("utf-8"),
        }
    )


async def send_http_error(send: Send, status: HTTPStatus) -> None:
    await send_http_response(send, status, {"detail": status[1]})
