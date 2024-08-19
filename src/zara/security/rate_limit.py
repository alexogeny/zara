import time
from collections import defaultdict
from functools import wraps
from typing import Awaitable, Callable

from zara.login.jwt import verify_jwt
from zara.types.http import send_http_response


class RateLimiter:
    def __init__(self, rate: int, period: int):
        self.rate = rate
        self.period = period
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        current_time = time.time()
        window_start = current_time - self.period

        self.requests[key] = [
            timestamp for timestamp in self.requests[key] if timestamp > window_start
        ]

        if len(self.requests[key]) < self.rate:
            self.requests[key].append(current_time)
            return True
        return False


def apply_rate_limit(router=None, limit: int = 100, period: int = 60):
    def decorator(func: Callable[..., Awaitable[None]]):
        limits = {
            "route": RateLimiter(limit, period),
            "router": RateLimiter(router.rate_limit[0], router.rate_limit[1]),
            "app": RateLimiter(router.app.rate_limit[0], router.app.rate_limit[1]),
        }

        @wraps(func)
        async def wrapper(request):
            scope, send = request["asgi"].scope, request["asgi"].send

            headers = dict(scope.get("headers", []))
            authorization = headers.get(b"authorization", b"").decode()
            token = authorization[7:] if authorization.startswith("Bearer ") else None
            jwt_payload = verify_jwt(token) if token else None
            # TODO: user specific rate limiting
            # user_id = jwt_payload.get("user_id") if jwt_payload else None

            # # if user_id and user_id in limits["user"]:
            # #     if not limits["user"][user_id].is_allowed(user_id):
            # #         request["error_was_raised"] = True
            # #         return await _rate_limit_exceeded_response(send)

            if limits["route"] and not limits["route"].is_allowed(scope["path"]):
                request["error_was_raised"] = True
                return await send_http_response(
                    send, 429, {"detail": "Rate limit exceeded"}
                )

            elif limits["router"] and not limits["router"].is_allowed(scope["path"]):
                request["error_was_raised"] = True
                return await send_http_response(
                    send, 429, {"detail": "Rate limit exceeded"}
                )

            elif limits["app"] and not limits["app"].is_allowed(scope["path"]):
                request["error_was_raised"] = True
                return await send_http_response(
                    send, 429, {"detail": "Rate limit exceeded"}
                )
            return await func(request)

        return wrapper

    return decorator
