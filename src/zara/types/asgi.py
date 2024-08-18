from typing import Any, Awaitable, Callable, TypeAlias

Scope: TypeAlias = dict
Receive: TypeAlias = Callable[[], Awaitable[bytes]]
Send: TypeAlias = Callable[[bytes], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

CallableAwaitable = Callable[..., Awaitable[Any]]


class ASGI:
    def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.scope = scope
        self.receive = receive
        self.send = send
