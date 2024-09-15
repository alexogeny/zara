import contextlib
import contextvars
from typing import Any


class Context:
    _db = contextvars.ContextVar("db")
    _request = contextvars.ContextVar("request")

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
    @contextlib.contextmanager
    def context(cls, db, request):
        token_db = cls._db.set(db)
        token_request = cls._request.set(request)
        try:
            yield
        finally:
            cls._db.reset(token_db)
            cls._request.reset(token_request)
