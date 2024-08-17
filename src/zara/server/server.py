from http import HTTPStatus
from typing import Any, Awaitable, Callable, Dict, List

from zara.config.config import Config
from zara.server.router import Router
from zara.types.asgi import Receive, Scope, Send
from zara.types.http import Http, send_http_error

GenericHandlerType = Callable[[], Awaitable[None]]
AsgiHandlerType = Callable[[Dict[str, Any]], Awaitable[None]]


class SimpleASGIApp:
    def __init__(self) -> None:
        self.routers: List[Router] = []
        self.before_request_handlers: List[AsgiHandlerType] = []
        self.after_request_handlers: List[AsgiHandlerType] = []
        self.startup_handlers: List[GenericHandlerType] = []
        self.shutdown_handlers: List[GenericHandlerType] = []
        self._config = None

    def add_router(self, router: Router) -> None:
        self.routers.append(router)

    @property
    def config(self):
        if self._config is None:
            self._config = Config("config.ini")
        return self._config

    def add_cors_headers(self, response: Dict[str, Any], origin: str) -> None:
        cors_config = self.config.cors
        if origin in cors_config.allowed_origins:
            response["headers"].extend(
                [
                    (b"access-control-allow-origin", origin.encode("utf-8")),
                    (
                        b"access-control-allow-methods",
                        cors_config.allowed_methods.encode("utf-8"),
                    ),
                    (
                        b"access-control-allow-headers",
                        cors_config.allowed_headers.encode("utf-8"),
                    ),
                ]
            )
            if cors_config.allow_credentials.lower() == "true":
                response["headers"].append(
                    (b"access-control-allow-credentials", b"true")
                )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        assert scope["type"] == "http"

        path = scope["path"]
        method = scope["method"]
        headers = scope["headers"]

        request = {
            "method": method,
            "path": path,
            "headers": headers,
            "query_string": scope["query_string"],
        }

        origin = dict(headers).get(b"origin", b"").decode("utf-8")

        for handler in self.before_request_handlers:
            await handler(request)

        response = None
        for router in self.routers:
            handler = await router.resolve(path, method)
            if handler:
                response = await handler(request)
                break

        if response is None:
            await send_http_error(send, HTTPStatus.NOT_FOUND)

        else:
            if origin:
                self.add_cors_headers(response, origin)
            await send(
                {
                    "type": Http.Response.Start,
                    "status": response["status"],
                    "headers": response["headers"],
                }
            )
            await send(
                {
                    "type": Http.Response.Body,
                    "body": response["body"],
                }
            )

        for handler in self.after_request_handlers:
            await handler(request)

    def route(
        self, path: str
    ) -> Callable[[Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]], None]:
        def decorator(
            func: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        ) -> None:
            self.routes[path] = func

        return decorator

    def add_before_request_handler(self, handler: AsgiHandlerType) -> None:
        self.before_request_handlers.append(handler)

    def add_after_request_handler(self, handler: AsgiHandlerType) -> None:
        self.after_request_handlers.append(handler)

    def add_startup_handler(self, handler: GenericHandlerType) -> None:
        self.startup_handlers.append(handler)

    def add_shutdown_handler(self, handler: GenericHandlerType) -> None:
        self.shutdown_handlers.append(handler)

    async def startup(self) -> None:
        for handler in self.startup_handlers:
            await handler()

    async def shutdown(self) -> None:
        for handler in self.shutdown_handlers:
            await handler()

    async def _dispatch(
        self, send, path: str, request: Dict[str, Any]
    ) -> Dict[str, Any]:
        for router in self.routers:
            response = await router.handle_request(path, request)
            if response["status"] != 404:
                return response
        await send_http_error(send, HTTPStatus.NOT_FOUND)


app = SimpleASGIApp()


async def log_request(request: Dict[str, Any]) -> None:
    print(f"Received request: {request['method']} {request['path']}")


async def log_response(request: Dict[str, Any]) -> None:
    print(f"Handled request: {request['method']} {request['path']}")


async def on_startup() -> None:
    print("Application is starting up...")


async def on_shutdown() -> None:
    print("Application is shutting down...")


app.add_before_request_handler(log_request)
app.add_after_request_handler(log_response)
app.add_startup_handler(on_startup)
app.add_shutdown_handler(on_shutdown)

router = Router()


@router.add_route(path="/", method="GET")
async def hello_world(request: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Hello, World!",
    }


@router.add_route(path="/goodbye", method="POST")
async def goodbye_world(request: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Goodbye, World!",
    }


app.add_router(router)
