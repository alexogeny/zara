from dataclasses import dataclass, field
from http import HTTPStatus
from typing import List, Tuple


class Response:
    def __init__(
        self,
        status_code: int = 200,
        headers: List[Tuple[bytes, bytes]] = [],
        body: bytes = b"",
    ):
        self.status_code = status_code
        self.headers = headers
        self.body = body

    def _create_status_line(self) -> bytes:
        status_code_str = str(self.status_code).encode()
        status_phrase = HTTPStatus(self.status_code).phrase.encode()
        return b"HTTP/1.1 " + status_code_str + b" " + status_phrase + b"\r\n"

    def _format_headers(self) -> bytes:
        return b"".join([key + b": " + value + b"\r\n" for key, value in self.headers])

    def make(self) -> bytes:
        return b"".join(
            [
                self._create_status_line(),
                self._format_headers(),
                b"\r\n" if self.body else b"",
                self.body,
            ]
        )


@dataclass
class ASGIResponse:
    status_code: int = 200
    headers: List[Tuple[bytes, bytes]] = field(default_factory=list)
    body: bytes = b""
    is_complete: bool = False

    def to_http(self, start_event: dict) -> bytes:
        """Converts the response into a raw HTTP response."""
        status_code = str(start_event["status"]).encode()
        headers = b"".join(
            [key + b": " + value + b"\r\n" for key, value in start_event["headers"]]
        )
        return b"HTTP/1.1 " + status_code + b" OK\r\n" + headers + b"\r\n"
