from functools import wraps
from http import HTTPStatus
from typing import Any, Awaitable, Callable, Dict, List, Optional

from zara.login.jwt import verify_jwt
from zara.types.http import Http


def auth_required(
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
):
    def decorator(func: Callable[..., Awaitable[None]]):
        @wraps(func)
        async def wrapper(scope: Dict[str, Any], receive: Callable, send: Callable):
            headers = dict(scope.get("headers", []))
            authorization = headers.get(b"authorization", b"").decode()

            if not authorization.startswith("Bearer "):
                await send(Http.Response.Start(status=HTTPStatus.FORBIDDEN))
                await send(
                    Http.Response.Detail(
                        message="Authorization header missing or malformed."
                    )
                )
                return

            token = authorization[7:]
            jwt_payload = verify_jwt(token)
            if jwt_payload is None:
                await send(Http.Response.Start(status=HTTPStatus.FORBIDDEN))
                await send(Http.Response.Detail(message="Invalid token"))
                return

            user_permissions = jwt_payload.get("permissions", [])
            user_roles = jwt_payload.get("roles", [])

            if permissions:
                if not all(p in user_permissions for p in permissions):
                    await send(Http.Response.Start(status=HTTPStatus.FORBIDDEN))
                    await send(Http.Response.Detail(message="Insufficient permissions"))
                    return

            if roles:
                if not any(r in user_roles for r in roles):
                    await send(Http.Response.Start(status=HTTPStatus.FORBIDDEN))
                    await send(Http.Response.Detail(message="Insufficient roles"))
                    return

            await func(scope, receive, send)

        return wrapper

    return decorator
