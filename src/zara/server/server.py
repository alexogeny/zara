from typing import Any, Awaitable, Callable, Dict, List

GenericHandlerType = Callable[[], Awaitable[None]]
AsgiHandlerType = Callable[[Dict[str, Any]], Awaitable[None]]


class Response:
    Start = "http.response.start"
    Body = "http.response.body"


class Http:
    Response = Response


# Generic ASGI application type based on scope, receive, send
ASGIApp = Callable[
    [
        Dict[str, Any],
        AsgiHandlerType,
        AsgiHandlerType,
    ],
    Awaitable[None],
]


class SimpleASGIApp:
    def __init__(self) -> None:
        self.routes: Dict[
            str, Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
        ] = {}
        self.before_request_handlers: List[AsgiHandlerType] = []
        self.after_request_handlers: List[AsgiHandlerType] = []
        self.startup_handlers: List[GenericHandlerType] = []
        self.shutdown_handlers: List[GenericHandlerType] = []

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Callable[[], Awaitable[Dict[str, Any]]],
        send: AsgiHandlerType,
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

        for handler in self.before_request_handlers:
            await handler(request)

        if path in self.routes:
            response = await self.routes[path](request)
        else:
            response = {
                "status": 404,
                "headers": [(b"content-type", b"text/plain")],
                "body": b"Not Found",
            }

        for handler in self.after_request_handlers:
            await handler(request)

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


@app.route("/")
async def hello_world(request):
    return {
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
        "body": b"Hello, world!",
    }
