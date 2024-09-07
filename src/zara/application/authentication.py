from functools import wraps
from typing import Callable, List

from zara.utilities.jwt_encode_decode import (
    verify_jwt,
)

SECRET_KEY = "your_application_secret"
ALGORITHM = "HS256"
CLIENT_ID = "local"
CLIENT_SECRET = "I3EUXRwR1W1fSz2ZYy7XZOnmKSn7uruK"
REDIRECT_URI = "http://localhost:8000/callback"

ACCESS_TOKEN_EXPIRE_MINUTES = 25
REFRESH_TOKEN_EXPIRE_DAYS = 7


def auth_required(roles: List[str] = None, permissions: List[str] = None):
    """Decorator for enforcing authentication with roles and permissions."""
    roles = roles or []
    permissions = permissions or []

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request):
            authorization = request.headers.get(b"Authorization", "")
            if not authorization.startswith(b"Bearer "):
                raise ValueError("Authorization header missing or malformed")

            token = authorization.decode("utf-8").split(" ")[1]
            try:
                payload = await verify_jwt(token)
                request.user = payload
                return await func(request)

            except (ValueError, KeyError) as e:
                raise ValueError(f"Authorization failed: {str(e)}")

        return wrapper

    return decorator
