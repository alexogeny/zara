from typing import Any, Callable, Dict, List
from urllib.parse import parse_qs

import orjson

from zara.application.events import Event, Listener
from zara.application.translation import I18n
from zara.errors import InternalServerError, ValidationError
from zara.server.events import EventBus


class Request:
    def __init__(
        self, scope: Dict[str, Any], receive: Callable, t: Callable = None, logger=None
    ):
        self.method = scope["method"]
        self.path = scope["path"]
        self.headers = dict(scope["headers"])
        self.query_parameters = parse_qs(scope.get("query_string", b"").decode())
        self._body = None
        self._receive = receive
        self.t = t
        self._logger = logger

    @property
    def logger(self):
        return self._logger

    async def body(self) -> bytes:
        """Lazily load the body when requested."""
        if self._body is None:
            body = b""
            more_body = True
            while more_body:
                message = await self._receive()
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
            self._body = body
        return self._body

    async def json(self) -> Dict[Any, Any]:
        await self.body()
        self.logger.debug(self._body)
        return orjson.loads(self._body)


class Route:
    def __init__(self, path: str, method: str, handler: Callable):
        self.path = path
        self.method = method
        self.handler = handler


class Router:
    def __init__(self, name: str = "default"):
        self.name = name
        self.routes: List[Route] = []

    def get(self, path: str):
        """Decorator to add a GET route."""

        def wrapper(handler: Callable):
            self.routes.append(Route(path=path, method="GET", handler=handler))
            return handler

        return wrapper

    def post(self, path: str):
        def wrapper(handler: Callable):
            self.routes.append(Route(path=path, method="POST", handler=handler))
            return handler

        return wrapper

    def resolve(self, method: str, path: str) -> Callable:
        """Find a matching route based on method and path."""
        for route in self.routes:
            if route.method == method and route.path == path:
                return route.handler
        return None


class ASGIApplication:
    def __init__(self):
        self.routers: List[Router] = []
        self._translations = {}
        self._i18n = I18n(self)
        self._event_bus: EventBus = None
        self._pending_listeners = []
        self.logger = None

    def add_router(self, router: Router):
        self.routers.append(router)

    def add_listener(self, event_name: str, listener: Callable):
        if self._event_bus is not None:
            self._event_bus.register_listener(event_name, Listener(listener))
        else:
            self._pending_listeners.append((event_name, Listener(listener)))

    def _attach_pending_listeners(self):
        for n, listener in self._pending_listeners:
            self._event_bus.register_listener(n, listener)

    def _attach_logger(self, logger):
        self.logger = logger

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        assert scope["type"] == "http"
        request = Request(scope, receive, logger=self.logger)
        self._event_bus.dispatch_event(Event("BeforeRequest", request))
        if request.path == "/favicon.ico":
            await self.send_favicon(send)
            self._event_bus.dispatch_event(Event("AfterRequest", request))

            return
        for router in self.routers:
            handler = router.resolve(request.method, request.path)
            if handler:
                request.t = self._i18n.get_translator("de")
                try:
                    response = await handler(request)
                except Exception as e:
                    if isinstance(e, InternalServerError):
                        self.logger.error(str(e))
                        await self.send_500(send)
                        self._event_bus.dispatch_event(Event("AfterRequest", request))
                        return
                    elif isinstance(e, ValidationError):
                        await self.send_400(send, data={"validation_errors": e.errors})
                        self._event_bus.dispatch_event(Event("AfterRequest", request))
                        return
                    self.logger.debug(e)
                await self.send_response(send, response)
                self._event_bus.dispatch_event(Event("AfterRequest", request))
                return
        await self.send_404(send, path=request.path)
        self._event_bus.dispatch_event(Event("AfterRequest", request))
        return

    async def send_response(self, send: Callable, body: bytes):
        """Send the HTTP response with body content."""
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})

    async def send_404(self, send: Callable, path="/"):
        """Send a 404 response when no route matches."""
        await self.send_error(send, 404, "Not Found")
        self.logger.debug(f"Returned a 404 for path: {path}")

    async def send_400(self, send: Callable, data="Bad Request"):
        await self.send_error(send, 400, data)

    async def send_error(self, send: Callable, status_code: int, detail: str):
        """Send an error response with the given status code and detail."""
        body = orjson.dumps({"detail": detail})
        content_length = str(len(body)).encode()

        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", content_length),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )

    async def send_500(self, send: Callable):
        await self.send_error(send, 500, "Internal Server Error")

    async def send_favicon(self, send: Callable):
        """Send a default response for favicon.ico."""
        favicon_data = b""  # Placeholder for actual favicon data
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"image/x-icon")],
            }
        )
        await send(
            {"type": "http.response.body", "body": favicon_data, "more_body": False}
        )
