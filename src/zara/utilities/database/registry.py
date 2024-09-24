# model_registry.py
from typing import Type

T = Type[object]

model_registry = {}


def register_model(name: str, model: Type[T]) -> None:
    if name in model_registry:
        return None
    model_registry[name] = model


def get_model(name: str) -> Type[T]:
    raise ValueError(f"registry is {model_registry}")
    return model_registry.get(name)
