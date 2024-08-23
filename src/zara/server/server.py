from http import HTTPStatus
import urllib.parse
from typing import Any, Awaitable, Callable, Dict, List

from zara.config.config import Config
from zara.server.router import Router
from zara.server.translation import I18n
from zara.types.asgi import ASGI, Receive, Scope, Send
from zara.types.http import Http, send_http_error

GenericHandlerType = Callable[[], Awaitable[None]]
AsgiHandlerType = Callable[[Dict[str, Any]], Awaitable[None]]


class SimpleASGIApp:
    def __init__(self, config=None) -> None:
        self.routers: list[Router] = []
        self.before_request_handlers: List[AsgiHandlerType] = []
        self.after_request_handlers: List[AsgiHandlerType] = []
        self.startup_handlers: List[GenericHandlerType] = []
        self.shutdown_handlers: List[GenericHandlerType] = []
        self._config = None
        self._raw_config = config
        self.rate_limit = (100, 60)  # 100 requests every 60 seconds
        self._translations = {}
        self._i18n = I18n(self)

    def add_router(self, router: Router) -> None:
        self.routers.append(router)
        router.app = self

    @cached_property
    def config(self):
        if self._config is None:
            if self._raw_config is not None:
                self._config = Config(config=self._raw_config)
            else:
                self._config = Config("config.ini")
        return self._config

    @cached_property
    def routers_with_root_last(self) -> list[Router]:
        non_root, root = [], []
        for router in self.routers:
            if router.name:
                non_root.append(router)
            else:
                root = [router]
        return non_root + root

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        asgi = ASGI(scope, receive, send, self.config)
        assert asgi.scope["type"] == "http"

        path = asgi.scope["path"]
        method = asgi.scope["method"]
        headers = asgi.scope["headers"]

        request = {
            "method": method,
            "path": path,
            "headers": headers,
            "params": {
                k: v[0] for k, v in urllib.parse.parse_qs(path.split("?")[1]).items()
            }
            if "?" in path
            else {},
            "asgi": asgi,
            "error_was_raised": False,
            "t": self._i18n.get_translator("en"),
        }

        for handler in self.before_request_handlers:
            await handler(request)

        response = None
        for router in self.routers_with_root_last:
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
