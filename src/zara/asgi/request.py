import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class ASGIRequest:
    http_method: str = ""
    path: str = ""
    headers: List[Tuple[bytes, bytes]] = field(default_factory=list)
    body_buffer: bytes = b""
    trigger_more_body: asyncio.Event = field(default_factory=asyncio.Event)
    last_body: bool = False

    def to_scope(self) -> Dict[str, Any]:
        """Creates the ASGI scope according to spec 3.0."""
        path_parts = self.path.split("?", 1)
        return {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "3.0"},
            "http_version": "1.1",
            "method": self.http_method,
            "scheme": "http",
            "path": path_parts[0],
            "query_string": path_parts[1].encode() if len(path_parts) > 1 else b"",
            "headers": self.headers,
        }

    async def receive_body(self, receive: Any):
        """Receives the request body in chunks."""
        while not self.last_body:
            event = await receive()
            if event["type"] == "http.request":
                self.body_buffer += event.get("body", b"")
                self.last_body = not event.get("more_body", False)
                if self.last_body:
                    break

    def to_event(self) -> Dict[str, Any]:
        """Convert the request into an ASGI event."""
        return {
            "type": "http.request",
            "body": self.body_buffer or b"",
            "more_body": False,
        }
