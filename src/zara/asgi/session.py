import asyncio
import gzip
import io
from typing import Any, Tuple

import brotli
import orjson
import zstandard as zstd
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

    async def get_encoding(self):
        """Find matching encoding from accept-encoding header tuple in self.request.headers."""
        self.app.logger.warning(self.request.headers)
        accept_encoding = next(
            (h for h in self.request.headers if h[0] == b"Accept-Encoding"),
            None,
        )
        self.app.logger.warning(accept_encoding)
        if not accept_encoding:
            return "plain"
        encodings = accept_encoding[1].decode("utf-8").split(", ")
        self.app.logger.warning(encodings)
        if "zstd" in encodings:
            return "zstd"
        if "br" in encodings:
            return "br"
        if "gzip" in encodings:
            return "gzip"
        if "deflate" in encodings:
            return "deflate"
        return "plain"

    def compress_response(self, body: bytes, encoding: str) -> Tuple[bytes, str]:
        if encoding == "zstd":
            return zstd.ZstdCompressor().compress(body), "zstd"
        elif encoding == "br":
            return brotli.compress(body), "br"
        elif encoding == "gzip":
            return gzip.compress(body), "gzip"
        elif encoding == "deflate":
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as f:
                f.write(body)
            return buf.getvalue(), "deflate"
        return body, "plain"

    async def send(self, event: dict):
        """ASGI send method to handle outgoing ASGI events."""

        if event["type"] == "http.response.start":
            self.cached_start_event = event

        elif event["type"] == "http.response.body":
            body = event.get("body", b"")
            # Detect if the body is not a byte string and handle encoding
            if not isinstance(body, bytes):
                if isinstance(body, (dict, list)):
                    # Encode dict or list to JSON using orjson
                    body = orjson.dumps(body)
                else:
                    # Convert other types to string and then to bytes
                    body = str(body).encode("utf-8")

            # Get preferred encoding
            encoding = await self.get_encoding()
            self.app.logger.warning(f"Using encoding {encoding}")
            # Compress the response body based on the preferred encoding
            compressed_body, content_encoding = self.compress_response(body, encoding)
            self.response.body = compressed_body

            content_length = len(compressed_body)
            if self.cached_start_event is not None:
                headers = self.cached_start_event.get("headers", [])
                self.app.logger.debug(event)
                for cookie in event.get("set_cookies", []):
                    self.app.logger.debug(cookie)
                    headers.append((b"set-cookie", cookie.encode("utf-8")))

                headers.append((b"content-encoding", content_encoding.encode("utf-8")))

                # Check if 'content-length' header is already present
                if not any(header[0] == b"content-length" for header in headers):
                    headers.append(
                        (b"content-length", str(content_length).encode("utf-8"))
                    )

                self.cached_start_event["headers"] = headers
                self.app.logger.warning(headers)
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
