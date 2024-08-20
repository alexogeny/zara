import json
import urllib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, List, Type, TypeVar


@dataclass
class BaseValidator(ABC):
    @abstractmethod
    def validate(self) -> List[Dict[str, Any]]:
        """
        Perform validation and return a list of errors.
        Each error should be a dictionary with at least the keys 'field' and 'message'.
        """
        pass


T = TypeVar("T", bound=BaseValidator)


def validate(query: Type[T] = None, json_body: Type[T] = None):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(request):
            scope, send, receive = (
                request["asgi"].scope,
                request["asgi"].send,
                request["asgi"].receive,
            )

            if query:
                query_params = query(
                    **{
                        k: v[0]
                        for k, v in urllib.parse.parse_qs(
                            scope.get("query_string", b"{}").decode("utf-8")
                        ).items()
                    }
                )
                validation_errors = query_params.validate()
                if validation_errors:
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 400,
                            "headers": [(b"content-type", b"application/json")],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": json.dumps({"errors": validation_errors}).encode(
                                "utf-8"
                            ),
                        }
                    )
                    return

            if json_body:
                body = await receive()
                json_data = json.loads(body["body"].decode("utf-8"))
                json_body_params = json_body(**json_data)
                validation_errors = json_body_params.validate()
                if validation_errors:
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 400,
                            "headers": [(b"content-type", b"application/json")],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": json.dumps({"errors": validation_errors}).encode(
                                "utf-8"
                            ),
                        }
                    )
                    return

            return await func(request)

        return wrapper

    return decorator
