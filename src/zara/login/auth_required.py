from functools import wraps
from typing import Awaitable, Callable, List, Optional

from zara.login.jwt import verify_jwt
from zara.types.http import send_http_response


def auth_required(
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
):
    def decorator(func: Callable[..., Awaitable[None]]):
        @wraps(func)
        async def wrapper(request):
            scope, send = request["asgi"].scope, request["asgi"].send
            headers = dict(scope.get("headers", []))
            authorization = headers.get(b"authorization", b"").decode()

            if not authorization.startswith("Bearer "):
                request["error_was_raised"] = True
                return await send_http_response(
                    send,
                    403,
                    {"detail": "Malformed authorization header"},
                )

            token = authorization[7:]
            jwt_payload = verify_jwt(token)
            if jwt_payload is None:
                request["error_was_raised"] = True
                return await send_http_response(send, 403, {"detail": "Invalid token"})

            user_permissions = jwt_payload.get("permissions", [])
            user_roles = jwt_payload.get("roles", [])

            if permissions:
                if not all(p in user_permissions for p in permissions):
                    request["error_was_raised"] = True
                    return await send_http_response(
                        send,
                        403,
                        {"detail": "Insufficient permissions"},
                    )

            if roles:
                if not any(r in user_roles for r in roles):
                    request["error_was_raised"] = True
                    return await send_http_response(
                        send, 403, {"detail": "Insufficient roles"}
                    )

            return await func(request)

        return wrapper

    return decorator
