from http import HTTPStatus
from typing import Any, Awaitable, Callable, Dict, List

from zara.config.config import Config
from zara.server.router import Router
from zara.types.asgi import ASGI, Receive, Scope, Send
from zara.types.http import Http, send_http_error

GenericHandlerType = Callable[[], Awaitable[None]]
AsgiHandlerType = Callable[[Dict[str, Any]], Awaitable[None]]


class SimpleASGIApp:
    def __init__(self) -> None:
        self.routers: list[Router] = []
        self.before_request_handlers: List[AsgiHandlerType] = []
        self.after_request_handlers: List[AsgiHandlerType] = []
        self.startup_handlers: List[GenericHandlerType] = []
        self.shutdown_handlers: List[GenericHandlerType] = []
        self._config = None
        self.rate_limit = (100, 60)  # 100 requests every 60 seconds

    def add_router(self, router: Router) -> None:
        self.routers.append(router)
        router.app = self

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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        asgi = ASGI(scope, receive, send)
        assert asgi.scope["type"] == "http"

        path = asgi.scope["path"]
        method = asgi.scope["method"]
        headers = asgi.scope["headers"]

        request = {
            "method": method,
            "path": path,
            "headers": headers,
            "query_string": asgi.scope["query_string"],
            "asgi": asgi,
            "error_was_raised": False,
        }

        origin = dict(headers).get(b"origin", b"").decode("utf-8")

        for handler in self.before_request_handlers:
            await handler(request)

        response = None
        non_root = [r for r in self.routers if r.name]
        root = [r for r in self.routers if not r.name]
        for router in non_root + root:
            if not await router.match(asgi.scope["path"]):
                continue

            handler = await router.resolve(asgi)
            if handler is not None:
                response = await handler(request)
            break

        if response is None:
            if request["error_was_raised"] is False:
                await send_http_error(asgi.send, HTTPStatus.NOT_FOUND)
        else:
            if origin:
                self.add_cors_headers(response, origin)
            await asgi.send(
                Http.Response.Start(
                    status=response["status"],
                    headers=response["headers"],
                )
            )
            await asgi.send(Http.Response.Body(content=response["body"]))

        for handler in self.after_request_handlers:
            await handler(request)

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
