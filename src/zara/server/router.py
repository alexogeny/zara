import http
from typing import Any, Awaitable, Callable, Dict, Self, Union

from zara.login.auth_required import auth_required
from zara.types.asgi import ASGI, CallableAwaitable
from zara.utils import camel_to_snake

WrappedRoute = Callable[..., CallableAwaitable]


class Route:
    def __init__(
        self,
        router,
        path: str,
        method: http.HTTPMethod,
        handler: Callable[..., Awaitable[Dict[str, Any]]],
        public: bool = True,
    ):
        self.method = method
        self.router = router
        self.path = path
        self.handler = handler
        self.public = public

    def __repr__(self):
        return f"[{self.router.name}]Route={self.path}"

    async def match(self, asgi: ASGI) -> bool:
        if self.method != asgi.scope["method"]:
            return False

        if not asgi.scope["path"].startswith(f"/{self.router.name}"):
            return False

        if self.public is False:
            return False

        return True


class Router:
    def __init__(self, name="") -> None:
        self.routes: list[Route] = []
        self.name = camel_to_snake(name)

    def add_route(
        self,
        router: Self,
        path: str,
        method: str,
        handler: Callable[..., Awaitable[Dict[str, Any]]],
        **kwargs: dict[Any, Any],
    ) -> None:
        route = Route(router, path, method, handler, **kwargs)
        self.routes.append(route)

    def route(
        self,
        path: str,
        method: str,
        permissions=None,
        roles=None,
        **kwargs: dict[Any, Any],
    ) -> WrappedRoute:
        def decorator(func: CallableAwaitable) -> CallableAwaitable:
            if permissions or roles:
                func = auth_required(permissions=permissions, roles=roles)(func)
            self.add_route(self, path, method, func, **kwargs)
            return func

        return decorator

    def get(self, path: str, **kwargs: Any):
        return self.route(path, "GET", **kwargs)

    def post(self, path: str, **kwargs: Any):
        return self.route(path, "POST", **kwargs)

    def patch(self, path: str, **kwargs: Any):
        return self.route(path, "PATCH", **kwargs)

    def delete(self, path: str, **kwargs: Any):
        return self.route(path, "DELETE", **kwargs)

    async def match(self, path: str) -> bool:
        if path.startswith(f"/{self.name}"):
            return True
        return False

    async def resolve(self, asgi: ASGI) -> Union[None, Awaitable[Dict[str, Any]]]:
        for route in self.routes:
            match_route = await route.match(asgi)
            if match_route is True:
                return route.handler
        return None
