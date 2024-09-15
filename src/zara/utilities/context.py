import contextlib
import contextvars
from typing import Any


class Context:
    _db = contextvars.ContextVar("db")
    _request = contextvars.ContextVar("request")
    _event_bus = contextvars.ContextVar("event_bus")

    @classmethod
    def set_db(cls, db: Any):
        cls._db.set(db)

    @classmethod
    def get_db(cls):
        return cls._db.get(None)

    @classmethod
    def set_request(cls, request: Any):
        cls._request.set(request)

    @classmethod
    def get_request(cls):
        return cls._request.get(None)

    @classmethod
    def set_event_bus(cls, event_bus: Any):
        cls._event_bus.set(event_bus)

    @classmethod
    def get_event_bus(cls):
        return cls._event_bus.get(None)

    @classmethod
    @contextlib.contextmanager
    def context(cls, db, request, event_bus):
        token_db = cls._db.set(db)
        token_request = cls._request.set(request)
        token_event_bus = cls._event_bus.set(event_bus)
        try:
            yield
        finally:
            cls._db.reset(token_db)
            cls._request.reset(token_request)
            cls._event_bus.reset(token_event_bus)
