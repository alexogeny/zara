import logging
import socket
from datetime import timedelta
from typing import Callable

import uvloop

from zara.application.events import Event, EventBus
from zara.utilities.dotenv import env
from zara.utilities.file_monitor import FileMonitor
from zara.utilities.logger import setup_logger

from .session import ASGISession


class ASGIServer:
    def __init__(self, app: Callable):
        self.app = app
        self.host = env.get("HOST", default="0.0.0.0")
        self.port = env.get("PORT", default=5000, cast_type=int)
        self.loop = uvloop.new_event_loop()
        self.server_socket = None
        self.file_monitor = FileMonitor("src")
        self.file_monitor.start()
        self.event_bus = EventBus()
        self.app._event_bus = self.event_bus
        self.logger = None

    def init_socket(self):
        """Initialize a non-blocking socket."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(100)
        self.server_socket.setblocking(False)

    async def serve_one_request(self, client_socket):
        """Handle one ASGI request from a client."""
        session = ASGISession(client_socket, self.app)
        await session.process()

    async def serve_forever(self):
        """Run the server forever, accepting connections."""
        self.init_socket()
        self.logger = await setup_logger(
            "Server",
            log_file="serverlogs.log",
            level=logging.DEBUG,
        )

        self.app._attach_pending_listeners()
        await self.event_bus.start()
        self.event_bus.schedule_event(
            Event("OnScheduledEvent", {}), delay=timedelta(seconds=10)
        )
        self.app._attach_logger(self.logger)
        self.app._check_duplicate_routes()
        self.logger.info(f"Serving on http://{self.host}:{self.port}")
        while True:
            client_socket, _ = await self.loop.sock_accept(self.server_socket)
            client_socket.setblocking(False)
            self.loop.create_task(self.serve_one_request(client_socket))

    async def run_once(self):
        """Run the server to handle only one request."""
        self.init_socket()

        client_socket, _ = await self.loop.sock_accept(self.server_socket)
        client_socket.setblocking(False)
        await self.serve_one_request(client_socket)
        client_socket.close()

    def run(self):
        """Run the server until interrupted."""

        try:
            self.loop.run_until_complete(self.serve_forever())
        except KeyboardInterrupt:
            print("Shutting down server...")
            self.loop.run_until_complete(self.event_bus.stop())
        finally:
            self.server_socket.close()
            self.loop.close()
