import re
from typing import Any, Callable, Dict, List
from urllib.parse import parse_qs

import orjson

from zara.application.events import Event, Listener
from zara.application.translation import I18n
from zara.errors import (
    AuthenticationError,
    DuplicateResourceError,
    InternalServerError,
    ResourceNotFoundError,
    ValidationError,
)

from .events import EventBus

param_pattern = re.compile(r"{(\w+):(\w+)}")


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
        self.cookies = []
        for name, value in self.parse_cookies().items():
            self.set_cookie(name, value)

    def parse_cookies(self):
        """Helper to parse cookies from the 'Cookie' header."""
        cookies = {}
        cookie_header = self.headers.get(b"cookie", b"").decode("utf-8")
        if cookie_header:
            for cookie in cookie_header.split(";"):
                name, value = cookie.strip().split("=")
                cookies[name] = value
        return cookies

    @property
    def logger(self):
        return self._logger

    def set_cookie(
        self, name, value, path="/", http_only=True, secure=True, same_site="Strict"
    ):
        """Helper function to set cookies in the response."""
        matching = next((c for c in self.cookies if f"{name}=" in c), None)
        if matching:
            return
        cookie = f"{name}={value}; Path={path}; HttpOnly={http_only}; Secure={secure}; SameSite={same_site}"
        self.cookies.append(cookie)

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

    def as_dict(self):
        return {
            "method": self.method,
            "path": self.path,
            "headers": self.headers,
            "query_parameters": self.query_parameters,
            "cookies": self.cookies,
        }


class Route:
    def __init__(self, path: str, method: str, handler: Callable):
        self.path = path
        self.method = method
        self.handler = handler
        self.param_patterns = self.build_param_patterns(path)

    @staticmethod
    def build_param_patterns(path: str):
        param_patterns = {}
        for match in param_pattern.finditer(path):
            param_name, param_type = match.groups()
            if param_type == "int":
                param_patterns[param_name] = int
            elif param_type == "str":
                param_patterns[param_name] = str
        return param_patterns

    def match(self, path: str):
        parts = param_pattern.split(self.path)
        regex = ""
        for i, part in enumerate(parts):
            if i % 3 == 0:
                regex += re.escape(part)  # static part
            elif i % 3 == 1:
                param_name = part
            elif i % 3 == 2:
                param_type = part  # type
                if param_type == "int":
                    regex += r"(?P<{}>\d+)".format(param_name)
                elif param_type == "str":
                    regex += r"(?P<{}>\w+)".format(param_name)
        match = re.match(f"^{regex}$", path)
        if match:
            return {
                name: self.param_patterns[name](value)
                for name, value in match.groupdict().items()
            }
        return None


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

    def resolve(self, method: str, path: str):
        for route in self.routes:
            if route.method == method:
                params = route.match(path)
                if params is not None:
                    return route.handler, params
        return None, {}


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
            handler, params = router.resolve(request.method, request.path)
            if handler:
                request.t = self._i18n.get_translator("de")
                try:
                    response = await handler(request, **params)
                except Exception as e:
                    await self.handle_exception(e, request, send)
                    return

                try:
                    await self.send_response(
                        send, response, set_cookies=request.cookies or []
                    )
                    self._event_bus.dispatch_event(Event("AfterRequest", request))
                    return
                except Exception as e:
                    await self.handle_exception(e, request, send)
                    return
        await self.send_404(send, path=request.path)
        self._event_bus.dispatch_event(Event("AfterRequest", request))
        return

    async def handle_exception(self, e, request, send):
        if isinstance(e, InternalServerError):
            self.logger.error(str(e))
            await self.send_500(send)
        elif isinstance(e, ValidationError):
            await self.send_400(send, data={"validation_errors": e.errors})
        elif isinstance(e, AuthenticationError):
            await self.send_401(send)
        elif isinstance(e, ResourceNotFoundError):
            await self.send_404(send, message=e.message)
        elif isinstance(e, DuplicateResourceError):
            await self.send_409(send, message=e.message)
        else:
            self._event_bus.dispatch_event(
                Event("UnhandledException", {"request": request, "exception": e})
            )
            await self.send_500(send)
        self._event_bus.dispatch_event(Event("AfterRequest", request))
        return

    async def send_response(
        self, send: Callable, body: bytes, set_cookies=[], status_code=200
    ):
        """Send the HTTP response with body content."""
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body if status_code == 200 else {"detail": body},
                "more_body": False,
                "set_cookies": set_cookies,
            }
        )

    async def send_404(self, send: Callable, message="Not Found", path="/"):
        """Send a 404 response when no route matches."""
        await self.send_error(send, 404, message)

    async def send_400(self, send: Callable, data="Bad Request"):
        await self.send_error(send, 400, data)

    async def send_401(self, send: Callable):
        await self.send_error(send, 401, "Unauthorized")

    async def send_409(self, send: Callable, message="Conflict", path="/"):
        """Send a 409 response when a resource already exists."""
        await self.send_error(send, 409, message)

    async def send_error(self, send: Callable, status_code: int, detail: str):
        """Send an error response with the given status code and detail."""
        await self.send_response(send, detail, status_code=status_code)

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
