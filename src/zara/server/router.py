from typing import Any, Awaitable, Callable, Dict


class Router:
    def __init__(self) -> None:
        self.routes: Dict[
            str, Dict[str, Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]]
        ] = {}

    def add_route(
        self, path: str, method: str
    ) -> Callable[[Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]], None]:
        def decorator(
            handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        ) -> None:
            if path not in self.routes:
                self.routes[path] = {}
            self.routes[path][method.upper()] = handler

        return decorator

    async def resolve(
        self, path: str, method: str
    ) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
        return self.routes.get(path, {}).get(method.upper())
