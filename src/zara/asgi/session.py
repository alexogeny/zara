import asyncio
from typing import Any

from httptools import HttpRequestParser

from zara.application.application import ASGIApplication

from .request import ASGIRequest
from .response import ASGIResponse


class ASGISession:
    def __init__(self, client_socket: Any, app: ASGIApplication):
        self.client_socket = client_socket
        self.app = app
        self.loop = asyncio.get_event_loop()
        self.request: ASGIRequest = ASGIRequest()
        self.response: ASGIResponse = ASGIResponse()
        self.receive_event = asyncio.Event()
        self.parser = HttpRequestParser(self)
        self.body_buffer = b""
        self.cached_start_event = None

    def on_url(self, url: bytes):
        """Called when the HTTP parser detects the request URL."""
        self.request.path = url.decode("utf-8")
        self.request.http_method = self.parser.get_method().decode("utf-8")

    def on_header(self, name: bytes, value: bytes):
        """Called for each header in the request."""
        self.request.headers.append((name, value))

    def on_body(self, body: bytes):
        """Called for each chunk of the request body."""
        self.body_buffer += body

    def on_message_complete(self):
        """Called when the request message is complete."""
        self.request.body_buffer = self.body_buffer
        self.receive_event.set()

    async def receive(self) -> dict:
        """ASGI receive method to provide data to the app."""
        await self.receive_event.wait()
        self.receive_event.clear()
        return self.request.to_event()

    async def send(self, event: dict):
        """ASGI send method to handle outgoing ASGI events."""
        if event["type"] == "http.response.start":
            self.cached_start_event = event

        elif event["type"] == "http.response.body":
            body = event.get("body", b"")
            self.response.body = body
            content_length = len(body)
            if self.cached_start_event is not None:
                headers = self.cached_start_event.get("headers", [])
                headers.append((b"content-length", str(content_length).encode("utf-8")))
                self.cached_start_event["headers"] = headers
                await self.loop.sock_sendall(
                    self.client_socket, self.response.to_http(self.cached_start_event)
                )
                self.cached_start_event = None
            await self.loop.sock_sendall(self.client_socket, self.response.body)

            if not event.get("more_body", False):
                self.response.is_complete = True
                self.client_socket.close()

    async def process(self):
        """Handles parsing the request and running the ASGI protocol."""
        while self.client_socket and self.client_socket.fileno() != -1:
            data = await self.loop.sock_recv(self.client_socket, 4096)
            if not data:
                break
            self.parser.feed_data(data)

            if self.receive_event.is_set():
                await self.app(self.request.to_scope(), self.receive, self.send)
