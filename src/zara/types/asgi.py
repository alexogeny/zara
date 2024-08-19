from typing import Any, Awaitable, Callable, Dict, TypeAlias

Scope: TypeAlias = dict
Receive: TypeAlias = Callable[[], Awaitable[bytes]]
Send: TypeAlias = Callable[[bytes], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

CallableAwaitable = Callable[..., Awaitable[Any]]


def make_csp(
    script="https://trustedscripts.example.com",
    style="https://trustedstyles.example.com",
    image="https://trustedimages.example.com",
):
    return (
        "default-src 'self'; "
        f"script-src 'self' {script}; "
        f"style-src 'self' {style}; "
        f"img-src 'self' data: {image}; "
        "frame-ancestors 'self'; "
        "form-action 'self'; "
        "block-all-mixed-content; "
        "upgrade-insecure-requests"
    ).encode("utf-8")


class ASGI:
    def __init__(self, scope: Scope, receive: Receive, send: Send, config):
        self.scope = scope
        self.receive = receive
        self.original_send = send
        self.config = config

    async def send(self, message: Dict[str, Any]) -> None:
        if message["type"] == "http.response.body":
            return await self.original_send(message)

        headers = dict(self.scope.get("headers", []))
        if message["type"] == "http.response.start" and hasattr(self.config, "csp"):
            message["headers"].append(
                (
                    b"content-security-policy",
                    make_csp(
                        script=self.config.csp.script,
                        style=self.config.csp.style,
                        image=self.config.csp.image,
                    ),
                )
            )
        if (origin := headers.get(b"origin", b"").decode("utf-8")) and hasattr(
            self.config, "cors"
        ):
            cors = self.config.cors
            if origin in cors.allowed_origins:
                message["headers"].extend(
                    [
                        (b"access-control-allow-origin", origin.encode("utf-8")),
                        (
                            b"access-control-allow-methods",
                            cors.allowed_methods.encode("utf-8"),
                        ),
                        (
                            b"access-control-allow-headers",
                            cors.allowed_headers.encode("utf-8"),
                        ),
                    ]
                )
                if cors.allow_credentials.lower() == "true":
                    message["headers"].append(
                        (b"access-control-allow-credentials", b"true")
                    )

        await self.original_send(message)
