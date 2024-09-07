async def dummy_app(scope, receive, send):
    assert scope["type"] == "http"
    # Start the response
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    # Send the body
    await send(
        {"type": "http.response.body", "body": b"Hello, World!", "more_body": False}
    )
