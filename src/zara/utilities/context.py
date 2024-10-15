import contextlib
import contextvars
from typing import Any


class Context:
    _db = contextvars.ContextVar("db")
    _request = contextvars.ContextVar("request")
    _event_bus = contextvars.ContextVar("event_bus")
    _customer = contextvars.ContextVar("customer")
    _user = contextvars.ContextVar("user")

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
    def set_customer(cls, customer: Any):
        cls._customer.set(customer)

    @classmethod
    def get_customer(cls):
        return cls._customer.get(None)

    @classmethod
    def set_user(cls, user: str):
        cls._user.set(user)

    @classmethod
    def get_user(cls):
        return cls._user.get(None)

    @classmethod
    @contextlib.contextmanager
    def context(cls, db, request, event_bus, customer, user=None):
        token_db = cls._db.set(db)
        token_request = cls._request.set(request)
        token_event_bus = cls._event_bus.set(event_bus)
        token_customer = cls._customer.set(customer)
        token_user = cls._user.set(user)
        try:
            yield
        finally:
            cls._db.reset(token_db)
            cls._request.reset(token_request)
            cls._event_bus.reset(token_event_bus)
            cls._customer.reset(token_customer)
            cls._user.reset(token_user)
