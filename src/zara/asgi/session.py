import asyncio
import gzip
import io
from typing import Any, Tuple

import brotli
import orjson
import zstandard as zstd
from httptools import HttpRequestParser

from zara.application.application import ASGIApplication
from zara.utilities.database import base

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
        accept_encoding = next(
            (h for h in self.request.headers if h[0] == b"Accept-Encoding"),
            None,
        )
        if not accept_encoding:
            return "plain"
        encodings = accept_encoding[1].decode("utf-8").split(", ")
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

    def generate_csp(self):
        """Generates a Content-Security-Policy header value based on the request headers.

        Ends up with default, script, style, image, frame, form, block mixed and upgrade insecure."""
        csp = {
            "default-src": "'self'",
            "script-src": "'self'",
            "style-src": "'self'",
            "img-src": "'self' data: https://trustedimages.example.com",
            "frame-ancestors": "'self'",
            "form-action": "'self'",
            "block-all-mixed-content": "",
            "upgrade-insecure-requests": "",
        }
        for header in self.request.headers:
            if header[0] == b"Content-Security-Policy":
                csp.update(header[1].decode("utf-8"))
        return "; ".join([f"{k} {v}" for k, v in csp.items()])

    def generate_hsts(self):
        """Generates a Strict-Transport-Security header value based on the request headers."""
        hsts = {
            "max-age": 31536000,
            "includeSubDomains": True,
            "preload": True,
        }
        for header in self.request.headers:
            if header[0] == b"Strict-Transport-Security":
                hsts.update(header[1].decode("utf-8"))
        return "; ".join([f"{k} {v}" for k, v in hsts.items()])

    async def send(self, event: dict):
        """ASGI send method to handle outgoing ASGI events."""

        if event["type"] == "http.response.start":
            self.cache_start_event(event)

        elif event["type"] == "http.response.body":
            await self.handle_response_body(event)

    def cache_start_event(self, event: dict):
        """Cache the response start event."""
        self.cached_start_event = event

    async def handle_response_body(self, event: dict):
        """Handle the response body event."""
        body = self.extract_body(event)
        body, is_json = await self.encode_body(body)
        content_type = "application/json" if is_json else "text/plain"
        self.app.logger.debug(f"Content type: {content_type}")

        encoding = await self.get_encoding()

        compressed_body, content_encoding = self.compress_response(body, encoding)
        self.response.body = compressed_body

        content_length = len(compressed_body)
        if self.cached_start_event is not None:
            self.append_headers(
                event, compressed_body, content_encoding, content_length, content_type
            )
            await self.send_start_event()

        await self.send_body()

        if not event.get("more_body", False):
            self.response.is_complete = True
            self.client_socket.close()

    def extract_body(self, event: dict) -> bytes:
        """Extract body from event."""
        return event.get("body", b"")

    async def encode_body(self, body) -> bytes:
        """Encode the body if needed."""
        is_json = False
        if not isinstance(body, bytes):
            if isinstance(body, (dict, list)):
                body = orjson.dumps(body)
                is_json = True
            elif isinstance(body, base.Model):
                body = orjson.dumps(body.as_dict())
                is_json = True
            else:
                body = str(body).encode("utf-8")

        return body, is_json

    def append_headers(
        self,
        event: dict,
        body: bytes,
        content_encoding: str,
        content_length: int,
        content_type: str,
    ):
        """Append necessary headers to the start event."""
        headers = self.cached_start_event.get("headers", [])
        self.app.logger.debug(event)
        for cookie in event.get("set_cookies", []):
            self.app.logger.debug(cookie)
            headers.append((b"set-cookie", cookie.encode("utf-8")))

        headers.append((b"content-encoding", content_encoding.encode("utf-8")))

        if not any(header[0] == b"content-length" for header in headers):
            headers.append((b"content-length", str(content_length).encode("utf-8")))

        content_type_header = [
            header for header in headers if header[0] == b"content-type"
        ]
        if content_type_header:
            headers = [header for header in headers if header[0] != b"content-type"]
            headers.append((b"content-type", content_type.encode("utf-8")))
        else:
            headers.append((b"content-type", content_type.encode("utf-8")))

        headers.append(
            (b"content-security-policy", self.generate_csp().encode("utf-8"))
        )
        headers.append((b"x-frame-options", b"SAMEORIGIN"))
        headers.append(
            (b"strict-transport-security", self.generate_hsts().encode("utf-8"))
        )

        if self.request.http_method == "OPTIONS":
            headers.extend(
                [
                    (b"access-control-allow-origin", b"*"),
                    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                    (b"access-control-allow-headers", b"Content-Type, Authorization"),
                    (b"access-control-allow-credentials", b"true"),
                    (b"content-length", b"0"),
                ]
            )

        self.cached_start_event["headers"] = headers
        self.app.logger.debug(self.cached_start_event)

    async def send_start_event(self):
        """Send the cached start event."""
        await self.loop.sock_sendall(
            self.client_socket, self.response.to_http(self.cached_start_event)
        )
        self.cached_start_event = None

    async def send_body(self):
        """Send the response body."""
        await self.loop.sock_sendall(self.client_socket, self.response.body)

    async def process(self):
        """Handles parsing the request and running the ASGI protocol."""
        while self.client_socket and self.client_socket.fileno() != -1:
            data = await self.loop.sock_recv(self.client_socket, 4096)
            if not data:
                break
            self.parser.feed_data(data)

            if self.receive_event.is_set():
                await self.app(self.request.to_scope(), self.receive, self.send)
