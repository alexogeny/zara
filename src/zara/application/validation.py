from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, Generic, List, Type, TypeVar, get_type_hints

import orjson

from zara.errors import ValidationError

TRequired = TypeVar("T")


class Required(Generic[TRequired]):
    def __init__(self, type_: TRequired):
        self.type_ = type_


def check_required_fields(instance) -> List[Dict[str, str]]:
    """Check if all required fields (with Required type) are set."""
    errors = []
    hints = get_type_hints(instance.__class__)

    for field, field_type in hints.items():
        if hasattr(field_type, "__origin__") and field_type.__origin__ is Required:
            value = getattr(instance, field, None)
            if value is None:
                errors.append(field)
    return errors


@dataclass
class ValidatorBase(ABC):
    @abstractmethod
    async def validate(self) -> List[Dict[str, Any]]:
        pass


T = TypeVar("T", bound=ValidatorBase)


def validate(validator: Type[T] = None):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(request):
            validation_errors = {}
            if request.method == "GET":
                validation_class = validator(**request.query_parameters)
            elif request.method != "GET":
                body = await request.body()
                body_json = orjson.loads(body) if body else {}
                validation_class = validator(**body_json)
            validation_errors = await validation_class.validate()
            if validation_errors:
                raise ValidationError(
                    [
                        {"field": e["field"], "message": request.t(e["message"])}
                        for e in validation_errors
                    ]
                )

            return await func(request)

        return wrapper

    return decorator
