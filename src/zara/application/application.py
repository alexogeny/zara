import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple
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
from zara.utilities.audit import create_audit_log
from zara.utilities.context import Context
from zara.utilities.database import AsyncDatabase
from zara.utilities.database.migrations import MigrationManager

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

    @property
    def __dict__(self):
        return self.as_dict()


class ExceptionWithDict:
    def __init__(self, e):
        self.e = e

    @property
    def __dict__(self):
        return str(self.e)


@dataclass
class Route:
    path: str
    method: str
    handler: Callable
    param_patterns: Dict[str, type] = None

    def __post_init__(self):
        if self.param_patterns is None:
            self.param_patterns = self.build_param_patterns(self.path)

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

    def match(self, path: str, logger) -> Dict[str, Any] | None:
        # Ensure both paths start with a slash and don't end with one
        route_path = "/" + self.path.strip("/")
        request_path = "/" + path.strip("/")
        logger.debug(f"Route path: {route_path}, request path: {request_path}")
        if route_path == request_path:
            return {}

        route_parts = route_path.split("/")
        path_parts = request_path.split("/")

        if len(route_parts) != len(path_parts):
            return None

        params = {}
        for route_part, path_part in zip(route_parts, path_parts):
            if route_part.startswith("{") and route_part.endswith("}"):
                param_name, param_type = route_part[1:-1].split(":")
                if param_type == "int":
                    try:
                        params[param_name] = int(path_part)
                    except ValueError:
                        return None
                elif param_type == "str":
                    params[param_name] = path_part
            elif route_part != path_part:
                return None

        return params


class Router:
    def __init__(self, name: str = "default", prefix: str = ""):
        self.name = name
        self.prefix = prefix.strip("/")  # Remove leading and trailing slashes
        self.routes: List[Route] = []

    def add_route(self, method: str, path: str, handler: Callable):
        full_path = f"/{self.prefix}/{path.lstrip('/')}".rstrip("/")
        if full_path == "":
            full_path = "/"
        self.routes.append(Route(path=full_path, method=method, handler=handler))

    def get(self, path: str):
        return lambda handler: self.add_route("GET", path, handler)

    def post(self, path: str):
        return lambda handler: self.add_route("POST", path, handler)

    def resolve(
        self, method: str, path: str, logger
    ) -> Tuple[Callable | None, Dict[str, Any]]:
        # Ensure path starts with a slash
        if not path.startswith("/"):
            path = "/" + path
        for route in self.routes:
            if route.method == method:
                params = route.match(path, logger)
                if params is not None:
                    return route.handler, params
        return None, {}

    def include_router(self, router: "Router"):
        for route in router.routes:
            full_path = f"/{self.prefix}/{route.path.lstrip('/')}".rstrip("/")
            if full_path == "":
                full_path = "/"
            self.routes.append(
                Route(path=full_path, method=route.method, handler=route.handler)
            )

    def __str__(self):
        return f"Router(name='{self.name}', prefix='{self.prefix}', routes={len(self.routes)})"


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

    def _internal_listeners(self):
        async def audit_listener(event: Event):
            event.logger.debug(f"Auditing event: {event.data}")
            await create_audit_log(event)

        self._event_bus.register_listener("AuditEvent", Listener(audit_listener))

        async def unhandled_exception_listener(event: Event):
            event.logger.error(
                f"Unhandled exception: {event.data['exception']}\n\nRequest: {event.data['request']}  {event}"
            )

        self._event_bus.register_listener(
            "UnhandledException", Listener(unhandled_exception_listener)
        )

    def _check_duplicate_routes(self) -> List[str]:
        all_routes = [route for router in self.routers for route in router.routes]
        self.logger.info(all_routes)
        duplicates = []
        seen = set()
        for route in all_routes:
            key = (route.method, route.path)
            self.logger.info(key)
            if key in seen:
                duplicates.append(f"{route.method} {route.path}")
            else:
                seen.add(key)
        if duplicates:
            self.logger.warning(f"Duplicate routes: {duplicates}")
        return duplicates

    # check migrations folder at root has migration files and throw if not
    def _check_migrations(self):
        if not MigrationManager().get_migration_files():
            self.logger.error(
                "No migrations found. Please run 'uv run migrate.py --create <migration_name>'"
            )
            raise sys.exit(1)

    async def get_x_subdomain(self, request: Request):
        result = "acme_corp"
        if request.headers.get("X-Subdomain"):
            result = request.headers.get("X-Subdomain")
        if request.headers.get("X-Forwarded-Host"):
            result = request.headers.get("X-Forwarded-Host").split(":")[0]
        if request.headers.get("Host"):
            split = request.headers.get("Host").split(".")
            if len(split) == 3:
                result = split[0]
        return result.lower().replace("-", "_")

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable):
        assert scope["type"] == "http"
        request = Request(scope, receive, logger=self.logger)
        self._event_bus.dispatch_event(Event("BeforeRequest", {"request": request}))
        if request.path == "/favicon.ico":
            await self.send_favicon(send)
            self._event_bus.dispatch_event(Event("AfterRequest", {"request": request}))
            return
        for router in self.routers:
            handler, params = router.resolve(request.method, request.path, self.logger)
            if handler:
                request.t = self._i18n.get_translator("de")
                x_subdomain = await self.get_x_subdomain(request)
                async with AsyncDatabase(x_subdomain, backend="postgresql") as db:
                    with Context.context(db, request, self._event_bus, x_subdomain):
                        try:
                            response = await handler(request, **params)
                        except Exception as e:
                            await self.handle_exception(e, request, send)
                            return

                try:
                    await self.send_response(
                        send, response, set_cookies=request.cookies or []
                    )
                    self._event_bus.dispatch_event(
                        Event("AfterRequest", {"request": request})
                    )
                    return
                except Exception as e:
                    await self.handle_exception(e, request, send)
                    return
        await self.send_404(send, path=request.path)
        self._event_bus.dispatch_event(Event("AfterRequest", {"request": request}))
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
                Event(
                    "UnhandledException",
                    {
                        "request": request,
                        "exception": self.convert_exception_to_class_with__dict__(e),
                    },
                )
            )
            await self.send_500(send)
        self._event_bus.dispatch_event(Event("AfterRequest", {"request": request}))
        return

    def convert_exception_to_class_with__dict__(self, e):
        exception_with_dict = ExceptionWithDict(e)
        return exception_with_dict

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
